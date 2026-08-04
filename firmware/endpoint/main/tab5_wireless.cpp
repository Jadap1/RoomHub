#include "tab5_wireless.hpp"

#include "bsp/m5stack_tab5.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "tab5_bringup.hpp"

namespace roomhub::board {
namespace {

constexpr char kTag[] = "roomhub_wireless";
bool wireless_powered = false;

bool succeeded_or_already_initialized(esp_err_t result)
{
    return result == ESP_OK || result == ESP_ERR_INVALID_STATE;
}

}  // namespace

bool power_on_tab5_wireless()
{
    ESP_LOGI(kTag, "Enabling the onboard ESP32-C6 power rail");
    const esp_err_t operation = bsp_feature_enable(BSP_FEATURE_WIFI, true);
    if (operation != ESP_OK) {
        ESP_LOGE(
            kTag,
            "Could not enable the ESP32-C6 power rail: %s",
            esp_err_to_name(operation)
        );
        return false;
    }
    wireless_powered = true;
    ESP_LOGI(kTag, "ESP32-C6 power rail enabled");
    return true;
}

Tab5WirelessScanResult scan_tab5_wifi()
{
    Tab5WirelessScanResult result;
    ESP_LOGI(kTag, "Starting credential-free ESP32-C6 Wi-Fi scan");
    if (!wireless_powered) {
        ESP_LOGE(kTag, "Cannot scan because the ESP32-C6 power rail is off");
        show_tab5_wireless_failed();
        return result;
    }

    ESP_LOGI(kTag, "Initializing the network interface");
    esp_err_t operation = esp_netif_init();
    if (!succeeded_or_already_initialized(operation)) {
        ESP_LOGE(
            kTag,
            "Network interface initialization failed: %s",
            esp_err_to_name(operation)
        );
        show_tab5_wireless_failed();
        return result;
    }
    operation = esp_event_loop_create_default();
    if (!succeeded_or_already_initialized(operation)) {
        ESP_LOGE(
            kTag,
            "Network event loop initialization failed: %s",
            esp_err_to_name(operation)
        );
        show_tab5_wireless_failed();
        return result;
    }
    if (esp_netif_create_default_wifi_sta() == nullptr) {
        ESP_LOGE(kTag, "Could not create the Wi-Fi station interface");
        show_tab5_wireless_failed();
        return result;
    }

    ESP_LOGI(kTag, "Initializing remote Wi-Fi over the C6 transport");
    wifi_init_config_t wifi_config = WIFI_INIT_CONFIG_DEFAULT();
    operation = esp_wifi_init(&wifi_config);
    if (operation != ESP_OK) {
        ESP_LOGE(
            kTag,
            "ESP32-C6 Wi-Fi initialization failed: %s",
            esp_err_to_name(operation)
        );
        show_tab5_wireless_failed();
        return result;
    }
    operation = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (operation == ESP_OK) {
        operation = esp_wifi_set_mode(WIFI_MODE_STA);
    }
    if (operation == ESP_OK) {
        operation = esp_wifi_start();
    }
    if (operation == ESP_OK) {
        operation = esp_wifi_scan_start(nullptr, true);
    }
    if (operation != ESP_OK) {
        ESP_LOGE(
            kTag,
            "ESP32-C6 network scan failed: %s",
            esp_err_to_name(operation)
        );
        show_tab5_wireless_failed();
        return result;
    }

    std::uint16_t network_count = 0;
    operation = esp_wifi_scan_get_ap_num(&network_count);
    if (operation != ESP_OK) {
        ESP_LOGE(
            kTag,
            "Could not read the network scan result: %s",
            esp_err_to_name(operation)
        );
        show_tab5_wireless_failed();
        return result;
    }

    result.radio_ready = true;
    result.network_count = network_count;
    ESP_LOGI(
        kTag,
        "ESP32-C6 scan complete: %u nearby networks (names not logged)",
        network_count
    );
    show_tab5_wireless_scan(network_count);
    return result;
}

}  // namespace roomhub::board
