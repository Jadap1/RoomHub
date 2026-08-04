#include "tab5_wireless.hpp"

#include <algorithm>
#include <cstring>

#include "bsp/m5stack_tab5.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "tab5_bringup.hpp"

namespace roomhub::board {
namespace {

constexpr char kTag[] = "roomhub_wireless";
constexpr EventBits_t kWifiConnected = BIT0;
constexpr EventBits_t kWifiFailed = BIT1;
bool wireless_powered = false;

bool succeeded_or_already_initialized(esp_err_t result)
{
    return result == ESP_OK || result == ESP_ERR_INVALID_STATE;
}

esp_err_t initialize_tab5_wifi()
{
    ESP_LOGI(kTag, "Initializing the network interface");
    esp_err_t operation = esp_netif_init();
    if (!succeeded_or_already_initialized(operation)) {
        return operation;
    }
    operation = esp_event_loop_create_default();
    if (!succeeded_or_already_initialized(operation)) {
        return operation;
    }
    if (esp_netif_create_default_wifi_sta() == nullptr) {
        return ESP_FAIL;
    }

    ESP_LOGI(kTag, "Initializing remote Wi-Fi over the C6 transport");
    wifi_init_config_t wifi_config = WIFI_INIT_CONFIG_DEFAULT();
    operation = esp_wifi_init(&wifi_config);
    if (operation == ESP_OK) {
        operation = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    }
    if (operation == ESP_OK) {
        operation = esp_wifi_set_mode(WIFI_MODE_STA);
    }
    if (operation == ESP_OK) {
        operation = esp_wifi_start();
    }
    return operation;
}

void wifi_event_handler(
    void *event_group,
    esp_event_base_t event_base,
    std::int32_t event_id,
    void *
)
{
    const EventGroupHandle_t events = static_cast<EventGroupHandle_t>(
        event_group
    );
    if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(events, kWifiConnected);
    } else if (
        event_base == WIFI_EVENT
        && event_id == WIFI_EVENT_STA_DISCONNECTED
    ) {
        xEventGroupSetBits(events, kWifiFailed);
    }
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

    esp_err_t operation = initialize_tab5_wifi();
    if (operation != ESP_OK) {
        ESP_LOGE(
            kTag,
            "ESP32-C6 Wi-Fi initialization failed: %s",
            esp_err_to_name(operation)
        );
        show_tab5_wireless_failed();
        return result;
    }
    operation = esp_wifi_scan_start(nullptr, true);
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

Tab5WirelessConnectionResult connect_tab5_wifi(
    const std::string &ssid,
    const std::string &password
)
{
    Tab5WirelessConnectionResult result;
    ESP_LOGI(kTag, "Connecting the ESP32-C6 to the provisioned Wi-Fi network");
    if (!wireless_powered) {
        ESP_LOGE(kTag, "Cannot connect because the ESP32-C6 power rail is off");
        show_tab5_wireless_failed();
        return result;
    }

    esp_err_t operation = initialize_tab5_wifi();
    if (operation != ESP_OK) {
        ESP_LOGE(
            kTag,
            "ESP32-C6 Wi-Fi initialization failed: %s",
            esp_err_to_name(operation)
        );
        show_tab5_wireless_failed();
        return result;
    }
    result.radio_ready = true;

    EventGroupHandle_t events = xEventGroupCreate();
    if (events == nullptr) {
        ESP_LOGE(kTag, "Could not allocate Wi-Fi connection events");
        show_tab5_wireless_failed();
        return result;
    }

    esp_event_handler_instance_t wifi_handler = nullptr;
    esp_event_handler_instance_t ip_handler = nullptr;
    operation = esp_event_handler_instance_register(
        WIFI_EVENT,
        WIFI_EVENT_STA_DISCONNECTED,
        wifi_event_handler,
        events,
        &wifi_handler
    );
    if (operation == ESP_OK) {
        operation = esp_event_handler_instance_register(
            IP_EVENT,
            IP_EVENT_STA_GOT_IP,
            wifi_event_handler,
            events,
            &ip_handler
        );
    }

    wifi_config_t station_config{};
    std::copy(ssid.begin(), ssid.end(), station_config.sta.ssid);
    std::copy(password.begin(), password.end(), station_config.sta.password);
    station_config.sta.threshold.authmode = WIFI_AUTH_OPEN;
    if (operation == ESP_OK) {
        operation = esp_wifi_set_config(WIFI_IF_STA, &station_config);
    }
    std::fill(
        std::begin(station_config.sta.password),
        std::end(station_config.sta.password),
        0
    );
    if (operation == ESP_OK) {
        operation = esp_wifi_connect();
    }

    EventBits_t connection_event = 0;
    if (operation == ESP_OK) {
        connection_event = xEventGroupWaitBits(
            events,
            kWifiConnected | kWifiFailed,
            pdTRUE,
            pdFALSE,
            pdMS_TO_TICKS(20000)
        );
    }

    if (ip_handler != nullptr) {
        esp_event_handler_instance_unregister(
            IP_EVENT,
            IP_EVENT_STA_GOT_IP,
            ip_handler
        );
    }
    if (wifi_handler != nullptr) {
        esp_event_handler_instance_unregister(
            WIFI_EVENT,
            WIFI_EVENT_STA_DISCONNECTED,
            wifi_handler
        );
    }
    vEventGroupDelete(events);

    if ((connection_event & kWifiConnected) == 0) {
        ESP_LOGE(
            kTag,
            "ESP32-C6 could not connect to the provisioned Wi-Fi network"
        );
        show_tab5_wireless_failed();
        return result;
    }

    result.connected = true;
    ESP_LOGI(kTag, "ESP32-C6 connected and received a network address");
    show_tab5_wireless_connected();
    return result;
}

}  // namespace roomhub::board
