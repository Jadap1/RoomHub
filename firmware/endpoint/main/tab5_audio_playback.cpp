#include "tab5_audio_playback.hpp"

#include <algorithm>
#include <cstdint>
#include <cstdlib>

#include "bsp/m5stack_tab5.h"
#include "esp_audio_dec_default.h"
#include "esp_audio_dec_reg.h"
#include "esp_audio_simple_dec.h"
#include "esp_audio_simple_dec_default.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_log.h"

namespace roomhub::board {
namespace {

constexpr char kTag[] = "roomhub_playback";
constexpr int kNetworkBufferBytes = 4096;
constexpr int kInitialPcmBufferBytes = 8192;
constexpr int kMaximumPcmBufferBytes = 64 * 1024;
constexpr int kRenderSampleRate = 16000;

struct PcmRenderer {
    std::uint32_t source_rate = 0;
    std::uint32_t source_channels = 0;
    std::uint32_t phase = 0;
    std::int16_t *buffer = nullptr;
    int capacity_samples = 0;
};

bool valid_audio_url(const std::string &url)
{
    return url.rfind("http://", 0) == 0 || url.rfind("https://", 0) == 0;
}

bool render_pcm(
    esp_codec_dev_handle_t speaker,
    PcmRenderer &renderer,
    const std::uint8_t *data,
    int size
)
{
    const auto *samples = reinterpret_cast<const std::int16_t *>(data);
    const int frame_count = size
        / static_cast<int>(sizeof(std::int16_t) * renderer.source_channels);
    const int maximum_output_samples = static_cast<int>(
        (static_cast<std::uint64_t>(frame_count) * kRenderSampleRate
         + renderer.source_rate - 1)
        / renderer.source_rate
    ) + 1;
    if (maximum_output_samples > renderer.capacity_samples) {
        auto *larger = static_cast<std::int16_t *>(std::realloc(
            renderer.buffer,
            maximum_output_samples * sizeof(std::int16_t)
        ));
        if (larger == nullptr) {
            return false;
        }
        renderer.buffer = larger;
        renderer.capacity_samples = maximum_output_samples;
    }

    int output_samples = 0;
    for (int frame = 0; frame < frame_count; ++frame) {
        std::int32_t mono = samples[frame * renderer.source_channels];
        if (renderer.source_channels == 2) {
            mono += samples[frame * renderer.source_channels + 1];
            mono /= 2;
        }
        renderer.phase += kRenderSampleRate;
        while (renderer.phase >= renderer.source_rate) {
            renderer.buffer[output_samples++] = static_cast<std::int16_t>(mono);
            renderer.phase -= renderer.source_rate;
        }
    }
    return output_samples == 0 || esp_codec_dev_write(
        speaker,
        renderer.buffer,
        output_samples * sizeof(std::int16_t)
    ) == ESP_CODEC_DEV_OK;
}

}  // namespace

PlaybackResult play_tab5_mp3_url(
    esp_codec_dev_handle_t speaker,
    const std::string &url,
    const std::atomic_bool *cancel_requested
)
{
    if (speaker == nullptr || !valid_audio_url(url)) {
        ESP_LOGE(kTag, "Cannot play Piper audio without a speaker and HTTP URL");
        return PlaybackResult::failed;
    }

    esp_http_client_config_t http_config{};
    http_config.url = url.c_str();
    http_config.crt_bundle_attach = esp_crt_bundle_attach;
    http_config.timeout_ms = 10000;
    http_config.buffer_size = kNetworkBufferBytes;
    http_config.user_agent = "RoomHub-ESP32-P4/1.0";
    esp_http_client_handle_t http = esp_http_client_init(&http_config);
    if (http == nullptr || esp_http_client_open(http, 0) != ESP_OK) {
        ESP_LOGE(kTag, "Could not open the Piper audio URL");
        if (http != nullptr) {
            esp_http_client_cleanup(http);
        }
        return PlaybackResult::failed;
    }
    const int64_t content_length = esp_http_client_fetch_headers(http);
    const int status = esp_http_client_get_status_code(http);
    if (status < 200 || status >= 300) {
        ESP_LOGE(kTag, "Piper audio request failed with HTTP %d", status);
        esp_http_client_close(http);
        esp_http_client_cleanup(http);
        return PlaybackResult::failed;
    }
    ESP_LOGI(
        kTag,
        "Streaming Piper audio: %lld encoded bytes",
        static_cast<long long>(content_length)
    );

    esp_audio_dec_register_default();
    esp_audio_simple_dec_register_default();
    esp_audio_simple_dec_cfg_t decoder_config{};
    decoder_config.dec_type = ESP_AUDIO_SIMPLE_DEC_TYPE_MP3;
    esp_audio_simple_dec_handle_t decoder = nullptr;
    esp_audio_err_t decode_result = esp_audio_simple_dec_open(
        &decoder_config,
        &decoder
    );
    auto *network_buffer = static_cast<std::uint8_t *>(
        std::malloc(kNetworkBufferBytes)
    );
    int pcm_capacity = kInitialPcmBufferBytes;
    auto *pcm_buffer = static_cast<std::uint8_t *>(std::malloc(pcm_capacity));
    bool speaker_open = false;
    PcmRenderer renderer;
    bool success = decode_result == ESP_AUDIO_ERR_OK
                   && network_buffer != nullptr && pcm_buffer != nullptr;

    bool cancelled = false;
    while (success) {
        if (cancel_requested != nullptr && cancel_requested->load()) {
            cancelled = true;
            break;
        }
        const int received = esp_http_client_read(
            http,
            reinterpret_cast<char *>(network_buffer),
            kNetworkBufferBytes
        );
        if (received < 0) {
            ESP_LOGE(kTag, "Piper audio download failed");
            success = false;
            break;
        }
        if (received == 0) {
            success = esp_http_client_is_complete_data_received(http);
            break;
        }

        esp_audio_simple_dec_raw_t input{};
        input.buffer = network_buffer;
        input.len = received;
        input.eos = esp_http_client_is_complete_data_received(http);
        while (success && input.len > 0) {
            if (cancel_requested != nullptr && cancel_requested->load()) {
                cancelled = true;
                break;
            }
            esp_audio_simple_dec_out_t output{};
            output.buffer = pcm_buffer;
            output.len = pcm_capacity;
            decode_result = esp_audio_simple_dec_process(
                decoder,
                &input,
                &output
            );
            if (decode_result == ESP_AUDIO_ERR_BUFF_NOT_ENOUGH) {
                if (output.needed_size <= 0
                    || output.needed_size > kMaximumPcmBufferBytes) {
                    success = false;
                    break;
                }
                auto *larger = static_cast<std::uint8_t *>(
                    std::realloc(pcm_buffer, output.needed_size)
                );
                if (larger == nullptr) {
                    success = false;
                    break;
                }
                pcm_buffer = larger;
                pcm_capacity = output.needed_size;
                continue;
            }
            if (decode_result != ESP_AUDIO_ERR_OK || input.consumed <= 0) {
                ESP_LOGE(kTag, "MP3 decode failed: %d", decode_result);
                success = false;
                break;
            }
            if (output.decoded_size > 0) {
                if (!speaker_open) {
                    esp_audio_simple_dec_info_t info{};
                    if (esp_audio_simple_dec_get_info(decoder, &info)
                            != ESP_AUDIO_ERR_OK
                        || info.bits_per_sample != 16
                        || info.sample_rate < 8000
                        || info.sample_rate > 48000
                        || info.channel < 1 || info.channel > 2) {
                        ESP_LOGE(kTag, "Piper audio has an unsupported PCM format");
                        success = false;
                        break;
                    }
                    esp_codec_dev_sample_info_t format{};
                    format.sample_rate = kRenderSampleRate;
                    format.channel = 1;
                    format.bits_per_sample = 16;
                    renderer.source_rate = info.sample_rate;
                    renderer.source_channels = info.channel;
                    success = bsp_feature_enable(BSP_FEATURE_SPEAKER, true)
                                  == ESP_OK
                              && esp_codec_dev_open(speaker, &format)
                                  == ESP_CODEC_DEV_OK
                              && esp_codec_dev_set_out_vol(speaker, 65)
                                  == ESP_CODEC_DEV_OK;
                    speaker_open = success;
                    ESP_LOGI(
                        kTag,
                        "Piper playback: %d Hz/%d channel -> 16000 Hz/mono",
                        static_cast<int>(info.sample_rate),
                        static_cast<int>(info.channel)
                    );
                }
                if (success && !render_pcm(
                    speaker,
                    renderer,
                    output.buffer,
                    output.decoded_size
                )) {
                    ESP_LOGE(kTag, "Could not write Piper PCM to the speaker");
                    success = false;
                }
            }
            input.len -= input.consumed;
            input.buffer += input.consumed;
        }
    }

    if (speaker_open) {
        esp_codec_dev_close(speaker);
    }
    bsp_feature_enable(BSP_FEATURE_SPEAKER, false);
    if (decoder != nullptr) {
        esp_audio_simple_dec_close(decoder);
    }
    esp_audio_simple_dec_unregister_default();
    esp_audio_dec_unregister_default();
    std::free(pcm_buffer);
    std::free(renderer.buffer);
    std::free(network_buffer);
    esp_http_client_close(http);
    esp_http_client_cleanup(http);
    const PlaybackResult result = cancelled
        ? PlaybackResult::cancelled
        : (success ? PlaybackResult::completed : PlaybackResult::failed);
    ESP_LOGI(
        kTag,
        "Piper playback %s",
        result == PlaybackResult::completed ? "finished"
        : (result == PlaybackResult::cancelled ? "cancelled" : "failed")
    );
    return result;
}

}  // namespace roomhub::board
