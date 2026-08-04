#include "esp_log.h"

#include "roomhub/endpoint_config.hpp"
#include "roomhub/voice_session.hpp"
#include "tab5_bringup.hpp"

namespace {
constexpr char kTag[] = "roomhub_endpoint";
}

extern "C" void app_main(void)
{
    const roomhub::voice::SessionConfig config{
        .silence_timeout_ms = 800,
        .maximum_capture_ms = 12000,
    };
    roomhub::voice::VoiceSession session(config);

    ESP_LOGI(kTag, "RoomHub endpoint firmware starting");
    ESP_LOGI(kTag, "Board profile: M5Stack Tab5");
    ESP_LOGI(kTag, "On-device wake model: wn9_jarvis_tts");

    bool endpoint_provisioned = false;
    const esp_err_t storage_result = roomhub::config::initialize_storage();
    if (storage_result != ESP_OK) {
        ESP_LOGE(
            kTag,
            "Configuration storage unavailable: %s",
            esp_err_to_name(storage_result)
        );
    } else {
        roomhub::config::EndpointConfigStore config_store;
        const roomhub::config::LoadResult config_result = config_store.load();
        if (config_result.status == roomhub::config::LoadStatus::ready) {
            endpoint_provisioned = true;
            ESP_LOGI(kTag, "Endpoint configuration loaded");
        } else if (
            config_result.status == roomhub::config::LoadStatus::not_provisioned
        ) {
            ESP_LOGW(kTag, "Endpoint provisioning required");
        } else {
            ESP_LOGE(
                kTag,
                "Endpoint configuration invalid or unreadable: %s",
                esp_err_to_name(config_result.error)
            );
        }
    }

    ESP_LOGI(
        kTag,
        "Privacy state: %s; network audio allowed: %s",
        roomhub::voice::to_string(session.state()),
        session.may_stream_audio() ? "yes" : "no"
    );

    const roomhub::board::Tab5BringUpResult board_result =
        roomhub::board::initialize_tab5(endpoint_provisioned);
    ESP_LOGI(
        kTag,
        "Tab5 bring-up: display=%s touch=%s microphone=%s speaker=%s",
        board_result.display_ready ? "ready" : "failed",
        board_result.touch_ready ? "ready" : "failed",
        board_result.microphone_ready ? "ready" : "failed",
        board_result.speaker_ready ? "ready" : "failed"
    );

    // Hardware capture and transport are composed in the next milestone.
    // Until then this application cannot open a network audio session.
}
