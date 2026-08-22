#include "tab5_wake_word.hpp"

#include <atomic>
#include <cstdlib>
#include <cstring>

#include "esp_afe_config.h"
#include "esp_afe_sr_iface.h"
#include "esp_afe_sr_models.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_wn_iface.h"
#include "esp_wn_models.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "model_path.h"
#include "roomhub_transport.hpp"
#include "tab5_audio_service.hpp"
#include "tab5_bringup.hpp"

namespace roomhub::board {
namespace {

constexpr char kTag[] = "roomhub_wake";
constexpr char kModelPartition[] = "model";
constexpr char kInputFormat[] = "M";
constexpr uint32_t kSampleRate = 16000;
constexpr uint8_t kBitsPerSample = 16;
constexpr float kMicrophoneGainDb = 42.0F;

esp_codec_dev_handle_t microphone_handle = nullptr;
srmodel_list_t *models = nullptr;
const esp_afe_sr_iface_t *afe_handle = nullptr;
esp_afe_sr_data_t *afe_data = nullptr;
std::atomic_bool detector_running{false};
std::atomic_bool microphone_muted{false};
roomhub::voice::VoiceSession *voice_session = nullptr;
std::uint32_t voice_playback_token = 0;

std::uint64_t now_ms()
{
    return static_cast<std::uint64_t>(esp_timer_get_time() / 1000);
}

void restore_private_listening_state()
{
    if (microphone_muted) show_tab5_microphone_muted();
    else show_tab5_wake_word_listening();
    ESP_LOGI(kTag, "Listening locally for Jarvis; network audio is disabled");
}

void microphone_feed_task(void *)
{
    const int samples_per_channel = afe_handle->get_feed_chunksize(afe_data);
    const int channel_count = afe_handle->get_feed_channel_num(afe_data);
    const size_t sample_count = static_cast<size_t>(samples_per_channel) *
                                static_cast<size_t>(channel_count);
    const size_t byte_count = sample_count * sizeof(int16_t);
    auto *samples = static_cast<int16_t *>(std::malloc(byte_count));
    if (samples == nullptr) {
        ESP_LOGE(kTag, "Could not allocate microphone feed buffer");
        detector_running = false;
        vTaskDelete(nullptr);
        return;
    }

    ESP_LOGI(
        kTag,
        "Microphone capture started: %lu Hz, %d channel, %d samples/frame",
        static_cast<unsigned long>(kSampleRate),
        channel_count,
        samples_per_channel
    );
    bool feed_backpressure = false;
    while (detector_running) {
        if (microphone_muted) {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }
        if (tab5_audio_output_active()) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        const int read_result = esp_codec_dev_read(
            microphone_handle,
            samples,
            static_cast<int>(byte_count)
        );
        if (read_result != ESP_CODEC_DEV_OK) {
            ESP_LOGE(kTag, "Microphone read failed: %d", read_result);
            detector_running = false;
            break;
        }
        const int fed_samples = afe_handle->feed(afe_data, samples);
        if (fed_samples < 0) {
            ESP_LOGE(
                kTag,
                "ESP-SR audio feed failed: %d samples accepted",
                fed_samples
            );
            detector_running = false;
            break;
        }
        if (fed_samples == 0) {
            // Fetch can pause briefly while the post-wake network session is
            // negotiated. A full AFE ring buffer is backpressure, not a
            // microphone failure; the oldest unconsumed frame is discarded.
            if (!feed_backpressure) {
                ESP_LOGW(
                    kTag,
                    "ESP-SR feed paused while its ring buffer is full"
                );
                feed_backpressure = true;
            }
            vTaskDelay(pdMS_TO_TICKS(10));
        } else if (feed_backpressure) {
            ESP_LOGI(kTag, "ESP-SR feed resumed");
            feed_backpressure = false;
        }
    }

    std::free(samples);
    vTaskDelete(nullptr);
}

void wake_word_fetch_task(void *)
{
    restore_private_listening_state();

    while (detector_running) {
        afe_fetch_result_t *result = afe_handle->fetch(afe_data);
        if (result == nullptr || result->ret_value == ESP_FAIL) {
            ESP_LOGE(kTag, "ESP-SR audio fetch failed");
            detector_running = false;
            break;
        }
        if (
            roomhub::transport::intercom_transmitting()
            && !microphone_muted
        ) {
            if (!roomhub::transport::send_intercom_audio(
                    result->data,
                    static_cast<std::size_t>(result->data_size)
                )) {
                roomhub::transport::cancel_intercom_call();
                restore_private_listening_state();
            }
            continue;
        }
        if (
            result->wakeup_state == WAKENET_DETECTED
            && !microphone_muted
            && voice_session->state()
                == roomhub::voice::SessionState::waiting_for_wake_word
        ) {
            ESP_LOGI(
                kTag,
                "Jarvis detected: model=%d word=%d volume=%.1f dB",
                result->wakenet_model_index,
                result->wake_word_index,
                static_cast<double>(result->data_volume)
            );
            show_tab5_wake_word_detected();
            interrupt_tab5_audio_for_voice_capture();
            const auto action = voice_session->on_wake_word_detected(now_ms());
            if (roomhub::voice::has_action(
                action,
                roomhub::voice::SessionAction::begin_audio_stream
            )) {
                if (!roomhub::transport::start_voice_audio()) {
                    voice_session->on_failure();
                    restore_private_listening_state();
                } else {
                    ESP_LOGI(
                        kTag,
                        "Command capture started; only post-wake audio is streaming"
                    );
                }
            }
            // The frame that triggered WakeNet is deliberately never sent.
            continue;
        }

        if (voice_session->may_stream_audio() && !microphone_muted) {
            const std::uint64_t current_time_ms = now_ms();
            if (result->vad_state == VAD_SPEECH) {
                voice_session->on_voice_activity(current_time_ms);
            }
            if (!roomhub::transport::send_voice_audio(
                result->data,
                static_cast<std::size_t>(result->data_size)
            )) {
                roomhub::transport::cancel_voice_audio();
                voice_session->on_failure();
                restore_private_listening_state();
                continue;
            }
            const auto action = voice_session->on_tick(current_time_ms);
            if (roomhub::voice::has_action(
                action,
                roomhub::voice::SessionAction::end_audio_stream
            )) {
                ESP_LOGI(kTag, "Command capture ended; network audio is disabled");
                if (!roomhub::transport::end_voice_audio()) {
                    voice_session->on_failure();
                    restore_private_listening_state();
                }
            }
        } else if (
            voice_session->state()
            == roomhub::voice::SessionState::awaiting_response
        ) {
            const auto response = roomhub::transport::voice_response_state();
            if (response == roomhub::transport::VoiceResponseState::ready) {
                const auto voice_response =
                    roomhub::transport::take_voice_response();
                const auto playback_action = voice_session->on_response_ready();
                bool playback_ok = true;
                if (roomhub::voice::has_action(
                        playback_action,
                        roomhub::voice::SessionAction::begin_playback
                    ) && !voice_response.speech_url.empty()) {
                    if (voice_response.mime_type != "audio/mpeg") {
                        ESP_LOGE(
                            kTag,
                            "Unsupported Piper media type: %s",
                            voice_response.mime_type.c_str()
                        );
                        playback_ok = false;
                    } else {
                        voice_playback_token = submit_tab5_audio(
                            "voice-response",
                            voice_response.speech_url,
                            voice_response.mime_type,
                            roomhub::audio::Priority::voice_assistant,
                            true
                        );
                        playback_ok = voice_playback_token != 0;
                    }
                }
                if (!playback_ok) {
                    voice_session->on_failure();
                    restore_private_listening_state();
                    continue;
                }
                if (voice_playback_token == 0) {
                    voice_session->on_playback_finished();
                    restore_private_listening_state();
                }
            } else if (
                response == roomhub::transport::VoiceResponseState::failed
            ) {
                voice_session->on_failure();
                restore_private_listening_state();
            }
        } else if (
            voice_session->state()
            == roomhub::voice::SessionState::playing_response
        ) {
            const auto playback = tab5_audio_state(voice_playback_token);
            if (playback == AudioPlaybackState::completed) {
                afe_handle->reset_buffer(afe_data);
                voice_session->on_playback_finished();
                voice_playback_token = 0;
                restore_private_listening_state();
            } else if (
                playback == AudioPlaybackState::interrupted
                || playback == AudioPlaybackState::failed
            ) {
                afe_handle->reset_buffer(afe_data);
                voice_session->on_failure();
                voice_playback_token = 0;
                restore_private_listening_state();
            }
        }
    }

    vTaskDelete(nullptr);
}

bool contains_jarvis_model(const srmodel_list_t *model_list)
{
    for (int index = 0; index < model_list->num; ++index) {
        const char *name = model_list->model_name[index];
        ESP_LOGI(kTag, "Speech model in flash: %s", name);
        if (std::strstr(name, ESP_WN_PREFIX) != nullptr &&
            std::strstr(name, "jarvis") != nullptr) {
            return true;
        }
    }
    return false;
}

}  // namespace

bool start_tab5_wake_word_detector(
    esp_codec_dev_handle_t microphone,
    roomhub::voice::VoiceSession &session
)
{
    if (detector_running) {
        return true;
    }
    if (microphone == nullptr) {
        ESP_LOGE(kTag, "Cannot start WakeNet without a microphone");
        return false;
    }

    esp_codec_dev_sample_info_t audio_format = {};
    audio_format.sample_rate = kSampleRate;
    audio_format.channel = 1;
    audio_format.bits_per_sample = kBitsPerSample;
    if (esp_codec_dev_set_in_gain(microphone, kMicrophoneGainDb) !=
        ESP_CODEC_DEV_OK) {
        ESP_LOGE(kTag, "Could not set microphone input gain");
        return false;
    }
    if (esp_codec_dev_open(microphone, &audio_format) != ESP_CODEC_DEV_OK) {
        ESP_LOGE(kTag, "Could not open the 16 kHz microphone stream");
        return false;
    }

    models = esp_srmodel_init(kModelPartition);
    if (models == nullptr || !contains_jarvis_model(models)) {
        ESP_LOGE(kTag, "The Jarvis WakeNet model was not found in flash");
        return false;
    }

    afe_config_t *config = afe_config_init(
        kInputFormat,
        models,
        AFE_TYPE_SR,
        AFE_MODE_LOW_COST
    );
    if (config == nullptr || config->wakenet_model_name == nullptr ||
        std::strstr(config->wakenet_model_name, "jarvis") == nullptr) {
        ESP_LOGE(kTag, "ESP-SR did not select the Jarvis WakeNet model");
        if (config != nullptr) {
            afe_config_free(config);
        }
        return false;
    }

    config->aec_init = false;
    config->se_init = false;
    config->memory_alloc_mode = AFE_MEMORY_ALLOC_MORE_PSRAM;
    ESP_LOGI(kTag, "WakeNet model selected: %s", config->wakenet_model_name);

    afe_handle = esp_afe_handle_from_config(config);
    if (afe_handle != nullptr) {
        afe_data = afe_handle->create_from_config(config);
    }
    afe_config_free(config);
    if (afe_handle == nullptr || afe_data == nullptr) {
        ESP_LOGE(kTag, "Could not create the ESP-SR audio front end");
        return false;
    }

    microphone_handle = microphone;
    voice_session = &session;
    detector_running = true;
    BaseType_t feed_created = xTaskCreate(
        microphone_feed_task,
        "wake_feed",
        6144,
        nullptr,
        5,
        nullptr
    );
    BaseType_t fetch_created = xTaskCreate(
        wake_word_fetch_task,
        "wake_fetch",
        4096,
        nullptr,
        5,
        nullptr
    );
    if (feed_created != pdPASS || fetch_created != pdPASS) {
        ESP_LOGE(kTag, "Could not start the WakeNet processing tasks");
        detector_running = false;
        return false;
    }
    return true;
}

void set_tab5_microphone_muted(bool muted)
{
    microphone_muted = muted;
    if (muted) {
        if (voice_session != nullptr) {
            roomhub::transport::cancel_voice_audio();
            roomhub::transport::cancel_intercom_call();
            voice_session->on_failure();
        }
        show_tab5_microphone_muted();
        ESP_LOGI(kTag, "Microphone muted; WakeNet and network capture disabled");
    } else {
        show_tab5_wake_word_listening();
        ESP_LOGI(kTag, "Microphone unmuted; local WakeNet listening resumed");
    }
}

bool tab5_microphone_muted()
{
    return microphone_muted.load();
}

}  // namespace roomhub::board
