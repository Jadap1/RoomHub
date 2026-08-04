#include "tab5_wake_word.hpp"

#include <atomic>
#include <cstdlib>
#include <cstring>

#include "esp_afe_config.h"
#include "esp_afe_sr_iface.h"
#include "esp_afe_sr_models.h"
#include "esp_log.h"
#include "esp_wn_iface.h"
#include "esp_wn_models.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "model_path.h"
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
    while (detector_running) {
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
        if (fed_samples <= 0) {
            ESP_LOGE(
                kTag,
                "ESP-SR audio feed failed: %d samples accepted",
                fed_samples
            );
            detector_running = false;
            break;
        }
    }

    std::free(samples);
    vTaskDelete(nullptr);
}

void wake_word_fetch_task(void *)
{
    show_tab5_wake_word_listening();
    ESP_LOGI(kTag, "Listening locally for Jarvis; network audio is disabled");

    while (detector_running) {
        afe_fetch_result_t *result = afe_handle->fetch(afe_data);
        if (result == nullptr || result->ret_value == ESP_FAIL) {
            ESP_LOGE(kTag, "ESP-SR audio fetch failed");
            detector_running = false;
            break;
        }
        if (result->wakeup_state == WAKENET_DETECTED) {
            ESP_LOGI(
                kTag,
                "Jarvis detected: model=%d word=%d volume=%.1f dB",
                result->wakenet_model_index,
                result->wake_word_index,
                static_cast<double>(result->data_volume)
            );
            show_tab5_wake_word_detected();
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

bool start_tab5_wake_word_detector(esp_codec_dev_handle_t microphone)
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

}  // namespace roomhub::board
