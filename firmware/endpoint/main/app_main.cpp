#include "esp_log.h"

#include "roomhub/endpoint_config.hpp"
#include "roomhub/voice_session.hpp"
#include "roomhub_transport.hpp"
#include "tab5_audio_service.hpp"
#include "tab5_bringup.hpp"
#include "tab5_wake_word.hpp"
#include "tab5_wireless.hpp"
#include "usb_provisioning.hpp"

namespace {
constexpr char kTag[] = "roomhub_endpoint";
}

extern "C" void app_main(void)
{
    const roomhub::voice::SessionConfig config{
        .silence_timeout_ms = 800,
        .maximum_capture_ms = 12000,
    };
    static roomhub::voice::VoiceSession session(config);

    ESP_LOGI(kTag, "RoomHub endpoint firmware starting");
    ESP_LOGI(kTag, "Board profile: M5Stack Tab5");
    ESP_LOGI(kTag, "On-device wake model: wn9_jarvis_tts");
    const bool wireless_powered = roomhub::board::power_on_tab5_wireless();
    ESP_LOGI(
        kTag,
        "ESP32-C6 power: %s",
        wireless_powered ? "ready" : "failed"
    );
    bool endpoint_provisioned = false;
    roomhub::config::EndpointConfig endpoint_config;
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
            endpoint_config = config_result.config;
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
    const bool audio_service_ready = roomhub::board::start_tab5_audio_service(
        board_result.speaker
    );
    ESP_LOGI(
        kTag,
        "Central audio service: %s",
        audio_service_ready ? "ready" : "failed"
    );

    if (!endpoint_provisioned && storage_result == ESP_OK) {
        roomhub::provisioning::run_usb_provisioning();
    }

    bool wireless_connected = false;
    if (endpoint_provisioned) {
        const roomhub::board::Tab5WirelessConnectionResult wireless_result =
            roomhub::board::connect_tab5_wifi(
                endpoint_config.wifi_ssid,
                endpoint_config.wifi_password
            );
        ESP_LOGI(
            kTag,
            "ESP32-C6 wireless connection: radio=%s network=%s",
            wireless_result.radio_ready ? "ready" : "failed",
            wireless_result.connected ? "connected" : "unavailable"
        );
        wireless_connected = wireless_result.connected;
    } else {
        const roomhub::board::Tab5WirelessScanResult wireless_result =
            roomhub::board::scan_tab5_wifi();
        ESP_LOGI(
            kTag,
            "ESP32-C6 wireless scan: radio=%s networks=%u",
            wireless_result.radio_ready ? "ready" : "failed",
            wireless_result.network_count
        );
    }

    if (wireless_connected) {
        const roomhub::transport::StartResult transport_result =
            roomhub::transport::start(endpoint_config);
        ESP_LOGI(
            kTag,
            "RoomHub control connection: service=%s registration=%s",
            transport_result.connected ? "connected" : "unavailable",
            transport_result.registered ? "accepted" : "pending"
        );
    }

    const bool wake_word_ready = roomhub::board::start_tab5_wake_word_detector(
        board_result.microphone,
        session
    );
    ESP_LOGI(
        kTag,
        "On-device Jarvis detection: %s",
        wake_word_ready ? "listening" : "failed"
    );
}
