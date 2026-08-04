#include "roomhub_transport.hpp"

#include <cstdint>
#include <string>

#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_log.h"
#include "esp_websocket_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"

namespace roomhub::transport {
namespace {

constexpr char kTag[] = "roomhub_transport";
constexpr EventBits_t kConnected = BIT0;
constexpr EventBits_t kRegistered = BIT1;
constexpr EventBits_t kFailed = BIT2;

struct TransportContext {
    EventGroupHandle_t events = nullptr;
    esp_websocket_client_handle_t client = nullptr;
    std::string endpoint_id;
    std::string registration;
};

TransportContext context;

std::string websocket_url(const std::string &roomhub_url)
{
    std::string result;
    if (roomhub_url.rfind("https://", 0) == 0) {
        result = "wss://" + roomhub_url.substr(8);
    } else {
        result = "ws://" + roomhub_url.substr(7);
    }
    while (!result.empty() && result.back() == '/') {
        result.pop_back();
    }
    if (result.size() < 3 || result.substr(result.size() - 3) != "/ws") {
        result += "/ws";
    }
    return result;
}

cJSON *create_message(const char *type, const std::string &endpoint_id)
{
    cJSON *message = cJSON_CreateObject();
    if (message == nullptr) {
        return nullptr;
    }
    cJSON_AddStringToObject(message, "version", "1.0");
    cJSON_AddStringToObject(message, "type", type);
    cJSON_AddStringToObject(message, "source", endpoint_id.c_str());
    cJSON_AddStringToObject(message, "target", "roomhub-core");
    return message;
}

std::string print_message(cJSON *message)
{
    char *encoded = cJSON_PrintUnformatted(message);
    cJSON_Delete(message);
    if (encoded == nullptr) {
        return {};
    }
    std::string result(encoded);
    cJSON_free(encoded);
    return result;
}

std::string registration_message(const std::string &endpoint_id)
{
    cJSON *message = create_message("endpoint.register", endpoint_id);
    if (message == nullptr) {
        return {};
    }
    cJSON *payload = cJSON_AddObjectToObject(message, "payload");
    cJSON_AddStringToObject(payload, "device_id", endpoint_id.c_str());
    cJSON_AddStringToObject(payload, "device_name", "RoomHub Tab5");
    cJSON_AddStringToObject(payload, "room", "Unassigned");
    cJSON *capabilities = cJSON_AddArrayToObject(payload, "capabilities");
    cJSON_AddItemToArray(capabilities, cJSON_CreateString("display"));
    cJSON_AddItemToArray(capabilities, cJSON_CreateString("speaker"));
    cJSON_AddItemToArray(capabilities, cJSON_CreateString("microphone"));
    cJSON_AddItemToArray(capabilities, cJSON_CreateString("touch"));
    return print_message(message);
}

std::string heartbeat_message(const std::string &endpoint_id)
{
    cJSON *message = create_message("endpoint.heartbeat", endpoint_id);
    if (message == nullptr) {
        return {};
    }
    cJSON *payload = cJSON_AddObjectToObject(message, "payload");
    cJSON_AddBoolToObject(payload, "connected", true);
    cJSON_AddStringToObject(
        payload,
        "privacy_state",
        "waiting_for_wake_word"
    );
    cJSON_AddBoolToObject(payload, "network_audio_allowed", false);
    return print_message(message);
}

bool send_text(
    esp_websocket_client_handle_t client,
    const std::string &message
)
{
    if (message.empty()) {
        return false;
    }
    return esp_websocket_client_send_text(
        client,
        message.c_str(),
        static_cast<int>(message.size()),
        pdMS_TO_TICKS(5000)
    ) == static_cast<int>(message.size());
}

void handle_data(TransportContext &transport, esp_websocket_event_data_t &data)
{
    if (data.op_code != 0x01
        || data.payload_offset != 0
        || data.data_len != data.payload_len) {
        return;
    }
    cJSON *message = cJSON_ParseWithLength(data.data_ptr, data.data_len);
    if (message == nullptr) {
        ESP_LOGW(kTag, "RoomHub sent an invalid control message");
        return;
    }
    const cJSON *type = cJSON_GetObjectItemCaseSensitive(message, "type");
    if (cJSON_IsString(type) && type->valuestring != nullptr) {
        if (std::string(type->valuestring) == "endpoint.registered") {
            xEventGroupSetBits(transport.events, kRegistered);
            ESP_LOGI(kTag, "Endpoint registration accepted by RoomHub");
        } else if (std::string(type->valuestring) != "endpoint.heartbeat_ack") {
            ESP_LOGI(kTag, "RoomHub control message received: %s", type->valuestring);
        }
    }
    cJSON_Delete(message);
}

void websocket_event_handler(
    void *handler_argument,
    esp_event_base_t,
    std::int32_t event_id,
    void *event_data
)
{
    auto &transport = *static_cast<TransportContext *>(handler_argument);
    auto &data = *static_cast<esp_websocket_event_data_t *>(event_data);
    if (event_id == WEBSOCKET_EVENT_CONNECTED) {
        xEventGroupClearBits(transport.events, kFailed);
        xEventGroupSetBits(transport.events, kConnected);
        ESP_LOGI(kTag, "Connected to the RoomHub control service");
    } else if (event_id == WEBSOCKET_EVENT_DATA) {
        handle_data(transport, data);
    } else if (
        event_id == WEBSOCKET_EVENT_DISCONNECTED
        || event_id == WEBSOCKET_EVENT_ERROR
    ) {
        xEventGroupClearBits(transport.events, kConnected | kRegistered);
        xEventGroupSetBits(transport.events, kFailed);
    }
}

void heartbeat_task(void *argument)
{
    auto &transport = *static_cast<TransportContext *>(argument);
    const std::string heartbeat = heartbeat_message(transport.endpoint_id);
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(10000));
        const EventBits_t state = xEventGroupGetBits(transport.events);
        if ((state & kConnected) != 0 && (state & kRegistered) == 0) {
            if (!send_text(transport.client, transport.registration)) {
                ESP_LOGW(kTag, "Could not resend endpoint registration");
            }
        } else if ((state & (kConnected | kRegistered))
                   == (kConnected | kRegistered)) {
            if (!send_text(transport.client, heartbeat)) {
                ESP_LOGW(kTag, "Could not send RoomHub heartbeat");
            }
        }
    }
}

}  // namespace

StartResult start(const roomhub::config::EndpointConfig &config)
{
    StartResult result;
    context.events = xEventGroupCreate();
    context.endpoint_id = config.endpoint_id;
    context.registration = registration_message(context.endpoint_id);
    if (context.events == nullptr || context.registration.empty()) {
        ESP_LOGE(kTag, "Could not allocate RoomHub transport state");
        return result;
    }

    const std::string url = websocket_url(config.roomhub_url);
    esp_websocket_client_config_t websocket_config{};
    websocket_config.uri = url.c_str();
    websocket_config.crt_bundle_attach = esp_crt_bundle_attach;
    websocket_config.network_timeout_ms = 10000;
    websocket_config.reconnect_timeout_ms = 5000;
    websocket_config.buffer_size = 2048;
    websocket_config.user_agent = "RoomHub-ESP32-P4/1.0";

    context.client = esp_websocket_client_init(&websocket_config);
    if (context.client == nullptr) {
        ESP_LOGE(kTag, "Could not initialize the RoomHub WebSocket client");
        return result;
    }
    esp_err_t operation = esp_websocket_register_events(
        context.client,
        WEBSOCKET_EVENT_ANY,
        websocket_event_handler,
        &context
    );
    if (operation == ESP_OK) {
        operation = esp_websocket_client_start(context.client);
    }
    if (operation != ESP_OK) {
        ESP_LOGE(kTag, "Could not start the RoomHub control connection");
        return result;
    }

    EventBits_t state = xEventGroupWaitBits(
        context.events,
        kConnected | kFailed,
        pdFALSE,
        pdFALSE,
        pdMS_TO_TICKS(15000)
    );
    result.connected = (state & kConnected) != 0;
    if (!result.connected) {
        ESP_LOGW(kTag, "RoomHub control service is not reachable");
        return result;
    }

    if (!send_text(context.client, context.registration)) {
        ESP_LOGW(kTag, "Could not send endpoint registration");
        return result;
    }

    state = xEventGroupWaitBits(
        context.events,
        kRegistered | kFailed,
        pdFALSE,
        pdFALSE,
        pdMS_TO_TICKS(10000)
    );
    result.registered = (state & kRegistered) != 0;
    if (!result.registered) {
        ESP_LOGW(kTag, "RoomHub did not accept endpoint registration");
        return result;
    }

    if (xTaskCreate(
        heartbeat_task,
        "roomhub_heartbeat",
        4096,
        &context,
        4,
        nullptr
    ) != pdPASS) {
        ESP_LOGW(kTag, "Could not start the RoomHub heartbeat task");
    }
    return result;
}

}  // namespace roomhub::transport
