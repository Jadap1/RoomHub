#include "tab5_audio_service.hpp"

#include <array>
#include <algorithm>
#include <atomic>
#include <limits>

#include "bsp/m5stack_tab5.h"
#include "esp_heap_caps.h"
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
std::atomic_bool intercom_ring_active{false};
std::atomic_bool intercom_ring_cancel{false};
std::int16_t *intercom_pcm_buffer = nullptr;
constexpr std::size_t kMaximumIntercomFrameBytes = 8192;
constexpr std::int32_t kIntercomReceiveGain = 3;
constexpr std::uint32_t kIntercomRingToken =
    std::numeric_limits<std::uint32_t>::max() - 1;
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

void intercom_ring_task(void *)
{
    constexpr int kSampleRate = 16000;
    constexpr std::array<int, 5> frequencies{784, 0, 988, 0, 784};
    constexpr std::array<int, 5> durations_ms{180, 70, 180, 70, 220};
    std::array<std::int16_t, 320> samples{};

    bool claimed = false;
    for (int attempt = 0; attempt < 12 && !claimed; ++attempt) {
        if (xSemaphoreTake(mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            if (playing_token.load() == 0 && !intercom_receive_active.load()) {
                playing_token = kIntercomRingToken;
                playing_priority = static_cast<std::uint8_t>(
                    roomhub::audio::Priority::intercom
                );
                claimed = true;
            }
            xSemaphoreGive(mutex);
        }
        if (!claimed) vTaskDelay(pdMS_TO_TICKS(50));
    }

    esp_codec_dev_sample_info_t format{};
    format.sample_rate = kSampleRate;
    format.channel = 1;
    format.bits_per_sample = 16;
    const bool speaker_enabled = claimed
        && bsp_feature_enable(BSP_FEATURE_SPEAKER, true) == ESP_OK;
    const bool codec_opened = speaker_enabled
        && esp_codec_dev_open(speaker_handle, &format) == ESP_CODEC_DEV_OK;
    const bool opened = codec_opened
        && esp_codec_dev_set_out_vol(
            speaker_handle,
            std::clamp(output_volume.load(), 0, 100)
        ) == ESP_CODEC_DEV_OK;

    if (opened) {
        std::uint32_t phase = 0;
        for (std::size_t segment = 0; segment < frequencies.size(); ++segment) {
            int remaining = durations_ms[segment] * kSampleRate / 1000;
            const std::uint32_t increment = frequencies[segment] == 0 ? 0
                : static_cast<std::uint32_t>(
                    (static_cast<std::uint64_t>(frequencies[segment]) << 32)
                    / kSampleRate
                );
            while (remaining > 0 && !intercom_ring_cancel.load()) {
                const int count = std::min(
                    remaining, static_cast<int>(samples.size())
                );
                for (int index = 0; index < count; ++index) {
                    if (increment == 0) {
                        samples[index] = 0;
                        continue;
                    }
                    phase += increment;
                    const std::uint32_t position = phase >> 16;
                    const std::int32_t triangle = position < 32768
                        ? static_cast<std::int32_t>(position * 2) - 32768
                        : 98303 - static_cast<std::int32_t>(position * 2);
                    samples[index] = static_cast<std::int16_t>(triangle / 3);
                }
                if (esp_codec_dev_write(
                        speaker_handle, samples.data(),
                        count * static_cast<int>(sizeof(std::int16_t))
                    ) != ESP_CODEC_DEV_OK) {
                    remaining = 0;
                    break;
                }
                remaining -= count;
            }
        }
    }
    if (codec_opened) {
        esp_codec_dev_close(speaker_handle);
    }
    if (speaker_enabled) {
        bsp_feature_enable(BSP_FEATURE_SPEAKER, false);
    }

    if (claimed && xSemaphoreTake(mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        if (playing_token.load() == kIntercomRingToken) {
            playing_token = 0;
            playing_priority = 0;
        }
        xSemaphoreGive(mutex);
    }
    intercom_ring_cancel = false;
    intercom_ring_active = false;
    vTaskDelete(nullptr);
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

bool play_tab5_intercom_ring()
{
    if (!service_started || output_volume.load() == 0
        || intercom_ring_active.exchange(true)) {
        return false;
    }
    intercom_ring_cancel = false;
    if (playing_token.load() != 0
        && playing_priority.load() < static_cast<std::uint8_t>(
            roomhub::audio::Priority::intercom
        )) {
        cancel_requested = true;
    }
    if (xTaskCreate(
            intercom_ring_task, "intercom_ring", 4096, nullptr, 6, nullptr
        ) != pdPASS) {
        intercom_ring_active = false;
        return false;
    }
    return true;
}

void stop_tab5_intercom_ring()
{
    intercom_ring_cancel = true;
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
    intercom_pcm_buffer = static_cast<std::int16_t *>(heap_caps_malloc(
        kMaximumIntercomFrameBytes,
        MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA | MALLOC_CAP_8BIT
    ));
    if (intercom_pcm_buffer == nullptr) {
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
    if (!intercom_receive_active || intercom_pcm_buffer == nullptr
        || data == nullptr || byte_count == 0
        || byte_count > kMaximumIntercomFrameBytes
        || byte_count % sizeof(std::int16_t) != 0) {
        return false;
    }
    const auto *samples = reinterpret_cast<const std::int16_t *>(data);
    const std::size_t sample_count = byte_count / sizeof(std::int16_t);
    for (std::size_t index = 0; index < sample_count; ++index) {
        const std::int32_t amplified =
            static_cast<std::int32_t>(samples[index]) * kIntercomReceiveGain;
        intercom_pcm_buffer[index] = static_cast<std::int16_t>(std::clamp(
            amplified,
            static_cast<std::int32_t>(std::numeric_limits<std::int16_t>::min()),
            static_cast<std::int32_t>(std::numeric_limits<std::int16_t>::max())
        ));
    }
    return esp_codec_dev_write(
        speaker_handle,
        intercom_pcm_buffer,
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
    heap_caps_free(intercom_pcm_buffer);
    intercom_pcm_buffer = nullptr;
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
