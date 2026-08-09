#include "tab5_audio_service.hpp"

#include <array>
#include <atomic>

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
            &cancel_requested
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
