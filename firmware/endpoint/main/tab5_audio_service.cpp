#include "tab5_audio_service.hpp"

#include <array>
#include <algorithm>
#include <atomic>
#include <limits>

#include "bsp/m5stack_tab5.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "tab5_audio_playback.hpp"

namespace roomhub::board {
namespace {

constexpr char kTag[] = "roomhub_audio";

struct Record {
    std::uint32_t token = 0;
    std::string request_id;
    std::string url;
    std::string mime_type;
    roomhub::audio::Priority priority = roomhub::audio::Priority::notification;
    bool retain_final_state = false;
    AudioPlaybackState state = AudioPlaybackState::unknown;
};

roomhub::audio::Scheduler scheduler;
std::array<Record, roomhub::audio::Scheduler::capacity + 1> records;
SemaphoreHandle_t mutex = nullptr;
esp_codec_dev_handle_t speaker_handle = nullptr;
std::atomic_uint32_t next_token{1};
std::atomic_uint32_t playing_token{0};
std::atomic_uint32_t playing_priority{0};
std::atomic_bool cancel_requested{false};
std::atomic_bool service_started{false};
std::atomic_int output_volume{65};
std::atomic_bool intercom_receive_active{false};
AudioEventCallback event_callback = nullptr;

Record *find_record(std::uint32_t token)
{
    for (auto &record : records) {
        if (record.token == token) {
            return &record;
        }
    }
    return nullptr;
}

Record *available_record()
{
    for (auto &record : records) {
        if (record.token == 0) {
            return &record;
        }
    }
    return nullptr;
}

void audio_service_task(void *)
{
    while (true) {
        Record request;
        if (xSemaphoreTake(mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            if (scheduler.has_active() && playing_token.load() == 0) {
                if (auto *record = find_record(scheduler.active().token)) {
                    request = *record;
                    record->state = AudioPlaybackState::playing;
                    playing_token = record->token;
                    playing_priority = static_cast<std::uint8_t>(
                        scheduler.active().priority
                    );
                    cancel_requested = false;
                }
            }
            xSemaphoreGive(mutex);
        }
        if (request.token == 0) {
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
        }

        ESP_LOGI(
            kTag,
            "Playing audio request %s at token %lu",
            request.request_id.c_str(),
            static_cast<unsigned long>(request.token)
        );
        if (event_callback != nullptr) {
            event_callback(request.request_id, AudioPlaybackState::playing);
        }
        const PlaybackResult result = play_tab5_mp3_url(
            speaker_handle,
            request.url,
            &cancel_requested,
            output_volume.load()
        );
        if (xSemaphoreTake(mutex, portMAX_DELAY) == pdTRUE) {
            if (auto *record = find_record(request.token)) {
                record->state = result == PlaybackResult::completed
                    ? AudioPlaybackState::completed
                    : (result == PlaybackResult::cancelled
                        ? AudioPlaybackState::interrupted
                        : AudioPlaybackState::failed);
                if (event_callback != nullptr) {
                    event_callback(record->request_id, record->state);
                }
                if (!record->retain_final_state) {
                    record->token = 0;
                }
            }
            if (scheduler.has_active()
                && scheduler.active().token == request.token) {
                scheduler.complete(request.token);
            }
            playing_token = 0;
            playing_priority = 0;
            cancel_requested = false;
            xSemaphoreGive(mutex);
        }
    }
}

}  // namespace

void set_tab5_audio_event_callback(AudioEventCallback callback)
{
    event_callback = callback;
}

void set_tab5_output_volume(int volume)
{
    output_volume = std::clamp(volume, 0, 100);
}

int tab5_output_volume()
{
    return output_volume.load();
}

bool start_tab5_intercom_receive()
{
    if (!service_started || intercom_receive_active.exchange(true)) {
        return false;
    }
    if (xSemaphoreTake(mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        intercom_receive_active = false;
        return false;
    }
    if (playing_token.load() != 0) {
        xSemaphoreGive(mutex);
        intercom_receive_active = false;
        return false;
    }
    playing_token = std::numeric_limits<std::uint32_t>::max();
    playing_priority = static_cast<std::uint8_t>(
        roomhub::audio::Priority::intercom
    );
    xSemaphoreGive(mutex);

    esp_codec_dev_sample_info_t format{};
    format.sample_rate = 16000;
    format.channel = 1;
    format.bits_per_sample = 16;
    const bool opened = bsp_feature_enable(BSP_FEATURE_SPEAKER, true) == ESP_OK
        && esp_codec_dev_open(speaker_handle, &format) == ESP_CODEC_DEV_OK
        && esp_codec_dev_set_out_vol(
            speaker_handle,
            std::clamp(output_volume.load(), 0, 100)
        ) == ESP_CODEC_DEV_OK;
    if (!opened) {
        stop_tab5_intercom_receive();
        ESP_LOGE(kTag, "Could not open the live intercom speaker stream");
        return false;
    }
    ESP_LOGI(kTag, "Live intercom speaker stream started");
    return true;
}

bool play_tab5_intercom_pcm(const std::uint8_t *data, std::size_t byte_count)
{
    return intercom_receive_active && data != nullptr && byte_count > 0
        && byte_count % sizeof(std::int16_t) == 0
        && esp_codec_dev_write(
            speaker_handle,
            const_cast<std::uint8_t *>(data),
            static_cast<int>(byte_count)
        ) == ESP_CODEC_DEV_OK;
}

void stop_tab5_intercom_receive()
{
    if (!intercom_receive_active.exchange(false)) {
        return;
    }
    esp_codec_dev_close(speaker_handle);
    bsp_feature_enable(BSP_FEATURE_SPEAKER, false);
    if (mutex != nullptr && xSemaphoreTake(mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        playing_token = 0;
        playing_priority = 0;
        xSemaphoreGive(mutex);
    }
    ESP_LOGI(kTag, "Live intercom speaker stream stopped");
}

bool start_tab5_audio_service(esp_codec_dev_handle_t speaker)
{
    if (service_started) {
        return true;
    }
    if (speaker == nullptr) {
        return false;
    }
    mutex = xSemaphoreCreateMutex();
    if (mutex == nullptr) {
        return false;
    }
    speaker_handle = speaker;
    if (xTaskCreate(
        audio_service_task,
        "roomhub_audio",
        12288,
        nullptr,
        5,
        nullptr
    ) != pdPASS) {
        return false;
    }
    service_started = true;
    return true;
}

std::uint32_t submit_tab5_audio(
    const std::string &request_id,
    const std::string &url,
    const std::string &mime_type,
    roomhub::audio::Priority priority,
    bool retain_final_state
)
{
    if (!service_started || request_id.empty() || url.empty()
        || mime_type != "audio/mpeg") {
        return 0;
    }
    if (xSemaphoreTake(mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return 0;
    }
    Record *record = available_record();
    if (record == nullptr) {
        xSemaphoreGive(mutex);
        return 0;
    }
    std::uint32_t token = next_token.fetch_add(1);
    if (token == 0) {
        token = next_token.fetch_add(1);
    }
    const auto decision = scheduler.submit({token, priority});
    if (decision.action == roomhub::audio::SubmitAction::rejected) {
        xSemaphoreGive(mutex);
        return 0;
    }
    *record = {
        .token = token,
        .request_id = request_id,
        .url = url,
        .mime_type = mime_type,
        .priority = priority,
        .retain_final_state = retain_final_state,
        .state = decision.action == roomhub::audio::SubmitAction::queued
            ? AudioPlaybackState::queued : AudioPlaybackState::playing,
    };
    if (decision.action == roomhub::audio::SubmitAction::interrupt) {
        cancel_requested = true;
    }
    xSemaphoreGive(mutex);
    return token;
}

bool cancel_tab5_audio(std::uint32_t token)
{
    if (mutex == nullptr
        || xSemaphoreTake(mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return false;
    }
    const bool was_playing = playing_token.load() == token;
    const bool cancelled = scheduler.cancel(token);
    if (cancelled) {
        if (auto *record = find_record(token)) {
            record->state = AudioPlaybackState::interrupted;
        }
        if (was_playing) {
            cancel_requested = true;
        }
    }
    xSemaphoreGive(mutex);
    return cancelled;
}

bool cancel_tab5_audio(const std::string &request_id)
{
    if (mutex == nullptr
        || xSemaphoreTake(mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return false;
    }
    Record *record = nullptr;
    for (auto &candidate : records) {
        if (candidate.request_id == request_id
            && candidate.state != AudioPlaybackState::completed
            && candidate.state != AudioPlaybackState::interrupted
            && candidate.state != AudioPlaybackState::failed) {
            record = &candidate;
            break;
        }
    }
    if (record == nullptr) {
        xSemaphoreGive(mutex);
        return false;
    }
    const std::uint32_t token = record->token;
    const bool was_playing = playing_token.load() == token;
    const bool cancelled = scheduler.cancel(token);
    if (cancelled) {
        record->state = AudioPlaybackState::interrupted;
        if (was_playing) {
            cancel_requested = true;
        }
    }
    xSemaphoreGive(mutex);
    return cancelled;
}

AudioPlaybackState tab5_audio_state(std::uint32_t token)
{
    if (mutex == nullptr
        || xSemaphoreTake(mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return AudioPlaybackState::unknown;
    }
    auto *record = find_record(token);
    const auto state = record == nullptr
        ? AudioPlaybackState::unknown : record->state;
    if (record != nullptr
        && (state == AudioPlaybackState::completed
            || state == AudioPlaybackState::interrupted
            || state == AudioPlaybackState::failed)) {
        record->token = 0;
    }
    xSemaphoreGive(mutex);
    return state;
}

bool tab5_audio_output_active()
{
    return playing_priority.load() >= static_cast<std::uint8_t>(
        roomhub::audio::Priority::voice_assistant
    );
}

void interrupt_tab5_audio_for_voice_capture()
{
    if (playing_token.load() == 0
        || playing_priority.load() >= static_cast<std::uint8_t>(
            roomhub::audio::Priority::voice_assistant
        )) {
        return;
    }
    cancel_tab5_audio(playing_token.load());
}

}  // namespace roomhub::board
