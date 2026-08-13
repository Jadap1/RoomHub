#include "roomhub_transport.hpp"

#include <atomic>
#include <cstdint>
#include <string>
#include <vector>

#include "cJSON.h"
#include "endpoint_ota.hpp"
#include "esp_app_desc.h"
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_websocket_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"
#include "freertos/stream_buffer.h"
#include "freertos/task.h"
#include "roomhub/recovery_backoff.hpp"
#include "tab5_audio_service.hpp"
#include "tab5_bringup.hpp"

namespace roomhub::transport {
namespace {

constexpr char kTag[] = "roomhub_transport";
constexpr EventBits_t kConnected = BIT0;
constexpr EventBits_t kRegistered = BIT1;
constexpr EventBits_t kFailed = BIT2;
constexpr EventBits_t kVoiceAudioReady = BIT3;
constexpr EventBits_t kVoiceResponseReady = BIT4;
constexpr EventBits_t kVoiceFailed = BIT5;
constexpr EventBits_t kClientStopped = BIT6;
constexpr std::size_t kMaximumAudioFrameBytes = 1024;
constexpr std::size_t kMaximumAudioBatchBytes = 8192;
constexpr std::size_t kAudioStreamBufferBytes = 384000;

struct TransportContext {
    EventGroupHandle_t events = nullptr;
    esp_websocket_client_handle_t client = nullptr;
    std::string endpoint_id;
    std::string roomhub_url;
    std::string registration;
    std::atomic_bool network_audio_allowed{false};
    std::atomic_bool voice_end_pending{false};
    std::atomic_bool voice_cancel_pending{false};
    std::atomic_bool reconnect_pending{false};
    std::atomic_bool restart_in_progress{false};
    std::atomic_uint32_t restart_delay_ms{0};
    StreamBufferHandle_t voice_audio_stream = nullptr;
    StaticStreamBuffer_t *voice_audio_stream_state = nullptr;
    std::uint8_t *voice_audio_storage = nullptr;
    SemaphoreHandle_t voice_response_mutex = nullptr;
    VoiceResponse voice_response;
    SemaphoreHandle_t firmware_status_mutex = nullptr;
    TaskHandle_t heartbeat_task_handle = nullptr;
    std::string firmware_request_id;
    std::string firmware_version;
    std::string firmware_status;
    std::string firmware_reason;
    unsigned int firmware_progress = 0;
    bool firmware_status_pending = false;
    roomhub::recovery::Backoff reconnect_backoff{1000, 30000};
};

TransportContext context;

bool send_text(
    esp_websocket_client_handle_t client,
    const std::string &message
);
bool voice_transport_ready();
cJSON *create_message(const char *type, const std::string &endpoint_id);
std::string print_message(cJSON *message);

void send_dashboard_action(const char *entity_id, const char *action, int value)
{
    if (entity_id == nullptr || context.client == nullptr) {
        return;
    }
    cJSON *message = create_message("dashboard.activate", context.endpoint_id);
    if (message == nullptr) {
        return;
    }
    cJSON *payload = cJSON_AddObjectToObject(message, "payload");
    cJSON_AddStringToObject(payload, "entity_id", entity_id);
    cJSON_AddStringToObject(payload, "action", action == nullptr ? "activate" : action);
    if (value >= 0) {
        cJSON_AddNumberToObject(payload, "value", value);
    }
    if (!send_text(context.client, print_message(message))) {
        ESP_LOGW(kTag, "Could not send dashboard action for %s", entity_id);
    }
}

void send_firmware_status(
    const std::string &request_id,
    const std::string &version,
    const char *status,
    unsigned int progress,
    const char *reason
)
{
    if (context.firmware_status_mutex == nullptr) return;
    if (xSemaphoreTake(context.firmware_status_mutex, pdMS_TO_TICKS(100)) != pdTRUE) return;
    context.firmware_request_id = request_id;
    context.firmware_version = version;
    context.firmware_status = status;
    context.firmware_progress = progress;
    context.firmware_reason = reason == nullptr ? "" : reason;
    context.firmware_status_pending = true;
    xSemaphoreGive(context.firmware_status_mutex);
    if (context.heartbeat_task_handle != nullptr) {
        xTaskNotifyGive(context.heartbeat_task_handle);
    }
}

void flush_firmware_status(TransportContext &transport)
{
    if (transport.firmware_status_mutex == nullptr
        || xSemaphoreTake(transport.firmware_status_mutex, 0) != pdTRUE) return;
    if (!transport.firmware_status_pending) {
        xSemaphoreGive(transport.firmware_status_mutex);
        return;
    }
    cJSON *message = create_message("firmware.status", transport.endpoint_id);
    if (message == nullptr) {
        xSemaphoreGive(transport.firmware_status_mutex);
        return;
    }
    cJSON *payload = cJSON_AddObjectToObject(message, "payload");
    cJSON_AddStringToObject(payload, "request_id", transport.firmware_request_id.c_str());
    cJSON_AddStringToObject(payload, "version", transport.firmware_version.c_str());
    cJSON_AddStringToObject(payload, "status", transport.firmware_status.c_str());
    cJSON_AddNumberToObject(payload, "progress", transport.firmware_progress);
    if (!transport.firmware_reason.empty()) {
        cJSON_AddStringToObject(payload, "reason", transport.firmware_reason.c_str());
    }
    if (send_text(transport.client, print_message(message))) {
        transport.firmware_status_pending = false;
    }
    xSemaphoreGive(transport.firmware_status_mutex);
}

void show_dashboard_payload(const cJSON *payload)
{
    if (!cJSON_IsObject(payload)) {
        return;
    }
    const cJSON *area_name = cJSON_GetObjectItemCaseSensitive(payload, "area_name");
    const cJSON *area_id = cJSON_GetObjectItemCaseSensitive(payload, "area_id");
    const cJSON *items = cJSON_GetObjectItemCaseSensitive(payload, "entities");
    const cJSON *media_items = cJSON_GetObjectItemCaseSensitive(payload, "media_players");
    if (!cJSON_IsString(area_name) || !cJSON_IsArray(items)) {
        return;
    }
    if (cJSON_IsString(area_id)) {
        const esp_err_t saved = roomhub::config::EndpointConfigStore().save_area_id(
            area_id->valuestring
        );
        if (saved != ESP_OK) {
            ESP_LOGW(kTag, "Could not persist dashboard area: %s", esp_err_to_name(saved));
        }
    }
    std::vector<roomhub::board::DashboardEntity> entities;
    const cJSON *item = nullptr;
    cJSON_ArrayForEach(item, items) {
        const cJSON *entity_id = cJSON_GetObjectItemCaseSensitive(item, "entity_id");
        const cJSON *name = cJSON_GetObjectItemCaseSensitive(item, "name");
        const cJSON *entity_type = cJSON_GetObjectItemCaseSensitive(item, "entity_type");
        const cJSON *state = cJSON_GetObjectItemCaseSensitive(item, "state");
        const cJSON *state_value = cJSON_IsObject(state)
            ? cJSON_GetObjectItemCaseSensitive(state, "state") : nullptr;
        const cJSON *available = cJSON_IsObject(state)
            ? cJSON_GetObjectItemCaseSensitive(state, "available") : nullptr;
        const cJSON *action = cJSON_GetObjectItemCaseSensitive(item, "action");
        const cJSON *pinned = cJSON_GetObjectItemCaseSensitive(item, "pinned");
        const cJSON *attributes = cJSON_IsObject(state)
            ? cJSON_GetObjectItemCaseSensitive(state, "attributes") : nullptr;
        const cJSON *current_temperature = cJSON_IsObject(attributes)
            ? cJSON_GetObjectItemCaseSensitive(attributes, "current_temperature") : nullptr;
        const cJSON *target_temperature = cJSON_IsObject(attributes)
            ? cJSON_GetObjectItemCaseSensitive(attributes, "temperature") : nullptr;
        const cJSON *hvac_action = cJSON_IsObject(attributes)
            ? cJSON_GetObjectItemCaseSensitive(attributes, "hvac_action") : nullptr;
        const cJSON *brightness = cJSON_IsObject(attributes)
            ? cJSON_GetObjectItemCaseSensitive(attributes, "brightness") : nullptr;
        const cJSON *percentage = cJSON_IsObject(attributes)
            ? cJSON_GetObjectItemCaseSensitive(attributes, "percentage") : nullptr;
        const cJSON *current_position = cJSON_IsObject(attributes)
            ? cJSON_GetObjectItemCaseSensitive(attributes, "current_position") : nullptr;
        if (!cJSON_IsString(entity_id) || !cJSON_IsString(name)
            || !cJSON_IsString(entity_type)) {
            continue;
        }
        entities.push_back({
            .entity_id = entity_id->valuestring,
            .entity_type = entity_type->valuestring,
            .name = name->valuestring,
            .state = cJSON_IsString(state_value) ? state_value->valuestring : "unknown",
            .hvac_action = cJSON_IsString(hvac_action)
                ? hvac_action->valuestring : "",
            .available = available == nullptr || cJSON_IsTrue(available),
            .actionable = cJSON_IsString(action)
                && std::string(action->valuestring) == "activate",
            .pinned = cJSON_IsTrue(pinned) != 0,
            .current_temperature = cJSON_IsNumber(current_temperature)
                ? static_cast<float>(current_temperature->valuedouble) : 0.0F,
            .target_temperature = cJSON_IsNumber(target_temperature)
                ? static_cast<float>(target_temperature->valuedouble) : 0.0F,
            .brightness = cJSON_IsNumber(brightness) ? brightness->valueint : 0,
            .percentage = cJSON_IsNumber(percentage) ? percentage->valueint : 0,
            .current_position = cJSON_IsNumber(current_position)
                ? current_position->valueint : 0,
            .has_current_temperature = cJSON_IsNumber(current_temperature) != 0,
            .has_target_temperature = cJSON_IsNumber(target_temperature) != 0,
            .has_brightness = cJSON_IsNumber(brightness) != 0,
            .has_percentage = cJSON_IsNumber(percentage) != 0,
            .has_current_position = cJSON_IsNumber(current_position) != 0,
        });
    }
    std::vector<roomhub::board::MediaPlayer> media_players;
    cJSON_ArrayForEach(item, media_items) {
        const cJSON *entity_id = cJSON_GetObjectItemCaseSensitive(item, "entity_id");
        const cJSON *name = cJSON_GetObjectItemCaseSensitive(item, "name");
        const cJSON *state = cJSON_GetObjectItemCaseSensitive(item, "state");
        const cJSON *state_value = cJSON_IsObject(state)
            ? cJSON_GetObjectItemCaseSensitive(state, "state") : nullptr;
        const cJSON *available = cJSON_IsObject(state)
            ? cJSON_GetObjectItemCaseSensitive(state, "available") : nullptr;
        const cJSON *attributes = cJSON_IsObject(state)
            ? cJSON_GetObjectItemCaseSensitive(state, "attributes") : nullptr;
        const cJSON *title = cJSON_IsObject(attributes)
            ? cJSON_GetObjectItemCaseSensitive(attributes, "media_title") : nullptr;
        const cJSON *artist = cJSON_IsObject(attributes)
            ? cJSON_GetObjectItemCaseSensitive(attributes, "media_artist") : nullptr;
        const cJSON *source = cJSON_IsObject(attributes)
            ? cJSON_GetObjectItemCaseSensitive(attributes, "source") : nullptr;
        const cJSON *volume = cJSON_IsObject(attributes)
            ? cJSON_GetObjectItemCaseSensitive(attributes, "volume_level") : nullptr;
        const cJSON *muted = cJSON_IsObject(attributes)
            ? cJSON_GetObjectItemCaseSensitive(attributes, "is_volume_muted") : nullptr;
        if (!cJSON_IsString(entity_id) || !cJSON_IsString(name)) {
            continue;
        }
        media_players.push_back({
            .entity_id = entity_id->valuestring,
            .name = name->valuestring,
            .state = cJSON_IsString(state_value) ? state_value->valuestring : "unknown",
            .media_title = cJSON_IsString(title) ? title->valuestring : "",
            .media_artist = cJSON_IsString(artist) ? artist->valuestring : "",
            .source = cJSON_IsString(source) ? source->valuestring : "",
            .available = available == nullptr || cJSON_IsTrue(available),
            .muted = cJSON_IsTrue(muted) != 0,
            .volume_percent = cJSON_IsNumber(volume)
                ? static_cast<int>(volume->valuedouble * 100.0) : 0,
        });
    }
    roomhub::board::show_tab5_dashboard(
        area_name->valuestring,
        entities,
        media_players,
        send_dashboard_action
    );
}

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

std::string registration_message(
    const std::string &endpoint_id,
    const std::string &area_id
)
{
    cJSON *message = create_message("endpoint.register", endpoint_id);
    if (message == nullptr) {
        return {};
    }
    cJSON *payload = cJSON_AddObjectToObject(message, "payload");
    cJSON_AddStringToObject(payload, "device_id", endpoint_id.c_str());
    cJSON_AddStringToObject(payload, "device_name", "RoomHub Tab5");
    cJSON_AddStringToObject(payload, "room", "Unassigned");
    if (!area_id.empty()) {
        cJSON_AddStringToObject(payload, "area_id", area_id.c_str());
    }
    cJSON_AddStringToObject(
        payload,
        "firmware_version",
        esp_app_get_description()->version
    );
    cJSON *capabilities = cJSON_AddArrayToObject(payload, "capabilities");
    cJSON_AddItemToArray(capabilities, cJSON_CreateString("display"));
    cJSON_AddItemToArray(capabilities, cJSON_CreateString("speaker"));
    cJSON_AddItemToArray(capabilities, cJSON_CreateString("microphone"));
    cJSON_AddItemToArray(capabilities, cJSON_CreateString("touch"));
    return print_message(message);
}

std::string heartbeat_message(
    const std::string &endpoint_id,
    bool network_audio_allowed
)
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
        network_audio_allowed ? "capturing_command" : "waiting_for_wake_word"
    );
    cJSON_AddBoolToObject(payload, "network_audio_allowed", network_audio_allowed);
    return print_message(message);
}

std::string voice_audio_message(
    const char *type,
    const std::string &endpoint_id,
    bool include_format
)
{
    cJSON *message = create_message(type, endpoint_id);
    if (message == nullptr) {
        return {};
    }
    cJSON *payload = cJSON_AddObjectToObject(message, "payload");
    if (include_format) {
        cJSON_AddNumberToObject(payload, "sample_rate", 16000);
        cJSON_AddNumberToObject(payload, "channels", 1);
        cJSON_AddStringToObject(payload, "format", "pcm_s16le");
    }
    return print_message(message);
}

std::string audio_status_message(
    const std::string &endpoint_id,
    const char *request_id,
    const char *status
)
{
    cJSON *message = create_message("audio.status", endpoint_id);
    if (message == nullptr) {
        return {};
    }
    cJSON *payload = cJSON_AddObjectToObject(message, "payload");
    cJSON_AddStringToObject(payload, "request_id", request_id);
    cJSON_AddStringToObject(payload, "status", status);
    return print_message(message);
}

roomhub::audio::Priority audio_priority(const cJSON *value)
{
    if (!cJSON_IsString(value) || value->valuestring == nullptr) {
        return roomhub::audio::Priority::notification;
    }
    const std::string priority(value->valuestring);
    if (priority == "emergency") return roomhub::audio::Priority::emergency;
    if (priority == "intercom") return roomhub::audio::Priority::intercom;
    if (priority == "voice_assistant") return roomhub::audio::Priority::voice_assistant;
    if (priority == "media") return roomhub::audio::Priority::media;
    return roomhub::audio::Priority::notification;
}

void send_audio_playback_event(
    const std::string &request_id,
    roomhub::board::AudioPlaybackState state
)
{
    const char *status = nullptr;
    switch (state) {
        case roomhub::board::AudioPlaybackState::playing:
            status = "playing";
            break;
        case roomhub::board::AudioPlaybackState::completed:
            status = "completed";
            break;
        case roomhub::board::AudioPlaybackState::interrupted:
            status = "interrupted";
            break;
        case roomhub::board::AudioPlaybackState::failed:
            status = "failed";
            break;
        default:
            return;
    }
    if (voice_transport_ready()) {
        send_text(
            context.client,
            audio_status_message(context.endpoint_id, request_id.c_str(), status)
        );
    }
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
        const std::string message_type(type->valuestring);
        if (message_type == "endpoint.registered") {
            xEventGroupSetBits(transport.events, kRegistered);
            roomhub::board::show_tab5_roomhub_registered();
            roomhub::ota::confirm_running_image();
            ESP_LOGI(kTag, "Endpoint registration accepted by RoomHub");
            const cJSON *payload = cJSON_GetObjectItemCaseSensitive(message, "payload");
            show_dashboard_payload(
                cJSON_IsObject(payload)
                    ? cJSON_GetObjectItemCaseSensitive(payload, "dashboard")
                    : nullptr
            );
        } else if (message_type == "room.dashboard") {
            show_dashboard_payload(cJSON_GetObjectItemCaseSensitive(message, "payload"));
        } else if (message_type == "firmware.update") {
            cJSON *payload = cJSON_GetObjectItemCaseSensitive(message, "payload");
            cJSON *version = cJSON_GetObjectItemCaseSensitive(payload, "version");
            cJSON *path = cJSON_GetObjectItemCaseSensitive(payload, "path");
            cJSON *sha256 = cJSON_GetObjectItemCaseSensitive(payload, "sha256");
            cJSON *size = cJSON_GetObjectItemCaseSensitive(payload, "size");
            cJSON *request_id = cJSON_GetObjectItemCaseSensitive(payload, "request_id");
            if (cJSON_IsString(request_id) && cJSON_IsString(version) && cJSON_IsString(path)
                && cJSON_IsString(sha256) && cJSON_IsNumber(size)
                && size->valuedouble > 0) {
                std::string base = transport.roomhub_url;
                while (!base.empty() && base.back() == '/') base.pop_back();
                const std::string update_path = path->valuestring;
                const std::string url = base
                    + (update_path.empty() || update_path.front() != '/' ? "/" : "")
                    + update_path;
                transport.network_audio_allowed = false;
                transport.voice_cancel_pending = true;
                xEventGroupClearBits(transport.events, kVoiceAudioReady);
                if (!roomhub::ota::start(
                    request_id->valuestring,
                    url,
                    version->valuestring,
                    static_cast<std::size_t>(size->valuedouble),
                    sha256->valuestring,
                    send_firmware_status
                )) {
                    send_firmware_status(
                        request_id->valuestring, version->valuestring,
                        "failed", 0, "command_rejected"
                    );
                    roomhub::board::show_tab5_firmware_failed();
                    ESP_LOGW(kTag, "Firmware update command rejected");
                }
            } else {
                ESP_LOGW(kTag, "Invalid firmware update command");
            }
        } else if (message_type == "voice.audio.ready") {
            transport.network_audio_allowed = true;
            xEventGroupClearBits(transport.events, kVoiceFailed);
            xEventGroupSetBits(transport.events, kVoiceAudioReady);
            ESP_LOGI(kTag, "RoomHub voice audio stream is ready");
        } else if (
            message_type == "voice.audio.rejected"
            || message_type == "voice.audio.failed"
        ) {
            transport.network_audio_allowed = false;
            xEventGroupClearBits(transport.events, kVoiceAudioReady);
            xEventGroupSetBits(transport.events, kVoiceFailed);
            ESP_LOGW(kTag, "RoomHub rejected or failed the voice audio stream");
        } else if (message_type.rfind("voice.intent.", 0) == 0) {
            transport.network_audio_allowed = false;
            const cJSON *payload = cJSON_GetObjectItemCaseSensitive(
                message,
                "payload"
            );
            const cJSON *speech = cJSON_IsObject(payload)
                ? cJSON_GetObjectItemCaseSensitive(payload, "speech")
                : nullptr;
            const cJSON *url = cJSON_IsObject(speech)
                ? cJSON_GetObjectItemCaseSensitive(speech, "url")
                : nullptr;
            const cJSON *mime_type = cJSON_IsObject(speech)
                ? cJSON_GetObjectItemCaseSensitive(speech, "mime_type")
                : nullptr;
            if (xSemaphoreTake(transport.voice_response_mutex, 0) == pdTRUE) {
                transport.voice_response = {};
                if (cJSON_IsString(url) && url->valuestring != nullptr
                    && cJSON_IsString(mime_type)
                    && mime_type->valuestring != nullptr) {
                    transport.voice_response.speech_url = url->valuestring;
                    transport.voice_response.mime_type = mime_type->valuestring;
                }
                xSemaphoreGive(transport.voice_response_mutex);
            }
            xEventGroupSetBits(transport.events, kVoiceResponseReady);
            ESP_LOGI(kTag, "RoomHub completed the voice intent request");
        } else if (message_type == "audio.play") {
            const cJSON *payload = cJSON_GetObjectItemCaseSensitive(message, "payload");
            const cJSON *request_id = cJSON_GetObjectItemCaseSensitive(payload, "request_id");
            const cJSON *url = cJSON_GetObjectItemCaseSensitive(payload, "url");
            const cJSON *mime_type = cJSON_GetObjectItemCaseSensitive(payload, "mime_type");
            const cJSON *priority = cJSON_GetObjectItemCaseSensitive(payload, "priority");
            const bool valid = cJSON_IsString(request_id) && request_id->valuestring
                && cJSON_IsString(url) && url->valuestring
                && cJSON_IsString(mime_type) && mime_type->valuestring;
            const std::uint32_t token = valid ? roomhub::board::submit_tab5_audio(
                request_id->valuestring,
                url->valuestring,
                mime_type->valuestring,
                audio_priority(priority)
            ) : 0;
            send_text(
                transport.client,
                audio_status_message(
                    transport.endpoint_id,
                    valid ? request_id->valuestring : "invalid",
                    token == 0 ? "rejected" : "accepted"
                )
            );
        } else if (message_type == "audio.stop") {
            const cJSON *payload = cJSON_GetObjectItemCaseSensitive(message, "payload");
            const cJSON *request_id = cJSON_GetObjectItemCaseSensitive(payload, "request_id");
            const bool stopped = cJSON_IsString(request_id)
                && request_id->valuestring
                && roomhub::board::cancel_tab5_audio(request_id->valuestring);
            send_text(
                transport.client,
                audio_status_message(
                    transport.endpoint_id,
                    cJSON_IsString(request_id) && request_id->valuestring
                        ? request_id->valuestring : "invalid",
                    stopped ? "stopped" : "not_found"
                )
            );
        } else if (message_type != "endpoint.heartbeat_ack") {
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
    if (event_id == WEBSOCKET_EVENT_CONNECTED) {
        transport.reconnect_backoff.reset();
        transport.reconnect_pending = false;
        xEventGroupClearBits(transport.events, kFailed);
        xEventGroupSetBits(transport.events, kConnected);
        roomhub::board::show_tab5_roomhub_connecting();
        ESP_LOGI(kTag, "Connected to the RoomHub control service");
    } else if (event_id == WEBSOCKET_EVENT_DATA) {
        if (event_data != nullptr) {
            handle_data(
                transport,
                *static_cast<esp_websocket_event_data_t *>(event_data)
            );
        }
    } else if (
        event_id == WEBSOCKET_EVENT_DISCONNECTED
        || event_id == WEBSOCKET_EVENT_ERROR
        || event_id == WEBSOCKET_EVENT_CLOSED
        || event_id == WEBSOCKET_EVENT_FINISH
    ) {
        if (transport.restart_in_progress.load()) {
            return;
        }
        xEventGroupClearBits(transport.events, kConnected | kRegistered);
        transport.network_audio_allowed = false;
        xEventGroupClearBits(transport.events, kVoiceAudioReady);
        xEventGroupSetBits(transport.events, kFailed | kVoiceFailed);
        xEventGroupSetBits(transport.events, kClientStopped);
        if (transport.reconnect_pending.exchange(true)) {
            return;
        }
        const std::uint32_t delay_ms = transport.reconnect_backoff.next_delay_ms();
        transport.restart_delay_ms = delay_ms;
        esp_websocket_client_set_reconnect_timeout(transport.client, delay_ms);
        roomhub::board::show_tab5_roomhub_retrying((delay_ms + 999) / 1000);
        ESP_LOGW(
            kTag,
            "RoomHub unavailable; reconnecting in %lu ms with local wake privacy active",
            static_cast<unsigned long>(delay_ms)
        );
    }
}

void heartbeat_task(void *argument)
{
    auto &transport = *static_cast<TransportContext *>(argument);
    transport.heartbeat_task_handle = xTaskGetCurrentTaskHandle();
    while (true) {
        const EventBits_t state = xEventGroupGetBits(transport.events);
        if ((state & kClientStopped) != 0) {
            const std::uint32_t delay_ms = transport.restart_delay_ms.exchange(0);
            if (delay_ms > 0) {
                vTaskDelay(pdMS_TO_TICKS(delay_ms));
            }
            transport.restart_in_progress = true;
            // Stop is safe from this maintenance task and also tears down a
            // half-open worker that no longer reports itself as connected.
            esp_websocket_client_stop(transport.client);
            xEventGroupClearBits(transport.events, kClientStopped);
            transport.reconnect_pending = false;
            roomhub::board::show_tab5_roomhub_connecting();
            const esp_err_t restart = esp_websocket_client_start(transport.client);
            transport.restart_in_progress = false;
            if (restart == ESP_OK) {
                ESP_LOGI(kTag, "Restarted the RoomHub WebSocket client after connection loss");
            } else {
                ESP_LOGW(kTag, "Could not restart RoomHub WebSocket client: %s", esp_err_to_name(restart));
                transport.reconnect_pending = true;
                transport.restart_delay_ms = transport.reconnect_backoff.next_delay_ms();
            }
            continue;
        }
        if ((state & kConnected) != 0 && (state & kRegistered) == 0) {
            if (!send_text(transport.client, transport.registration)) {
                ESP_LOGW(kTag, "Could not resend endpoint registration");
            }
        } else if ((state & (kConnected | kRegistered))
                   == (kConnected | kRegistered)) {
            // The ESP32-C6 transport cannot reliably service WebSocket writes
            // while its HTTP connection is streaming the OTA image. Keep the
            // latest status queued and resume transport traffic afterward.
            if (!roomhub::ota::network_busy()) {
                flush_firmware_status(transport);
                const std::string heartbeat = heartbeat_message(
                    transport.endpoint_id,
                    transport.network_audio_allowed.load()
                );
                if (!send_text(transport.client, heartbeat)) {
                ESP_LOGW(kTag, "Could not send RoomHub heartbeat");
                xEventGroupClearBits(transport.events, kConnected | kRegistered);
                transport.network_audio_allowed = false;
                xEventGroupSetBits(
                    transport.events,
                    kFailed | kVoiceFailed | kClientStopped
                );
                if (!transport.reconnect_pending.exchange(true)) {
                    transport.restart_delay_ms =
                        transport.reconnect_backoff.next_delay_ms();
                }
                roomhub::board::show_tab5_roomhub_retrying(
                    (transport.restart_delay_ms.load() + 999) / 1000
                );
                }
            }
        }
        const bool registered = (state & (kConnected | kRegistered))
            == (kConnected | kRegistered);
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(registered ? 10000 : 1000));
    }
}

bool voice_transport_ready()
{
    if (context.events == nullptr || context.client == nullptr) {
        return false;
    }
    const EventBits_t state = xEventGroupGetBits(context.events);
    return !roomhub::ota::in_progress()
        && (state & (kConnected | kRegistered)) == (kConnected | kRegistered);
}

void fail_voice_stream(TransportContext &transport)
{
    transport.network_audio_allowed = false;
    xEventGroupClearBits(transport.events, kVoiceAudioReady);
    xEventGroupSetBits(transport.events, kVoiceFailed);
}

void voice_sender_task(void *argument)
{
    auto &transport = *static_cast<TransportContext *>(argument);
    auto *audio_batch = static_cast<std::uint8_t *>(heap_caps_malloc(
        kMaximumAudioBatchBytes,
        MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT
    ));
    if (audio_batch == nullptr) {
        ESP_LOGE(kTag, "Could not allocate the voice network batch buffer");
        fail_voice_stream(transport);
        vTaskDelete(nullptr);
        return;
    }

    while (true) {
        if (transport.voice_cancel_pending.exchange(false)) {
            xStreamBufferReset(transport.voice_audio_stream);
            transport.voice_end_pending = false;
            if (!send_text(
                transport.client,
                voice_audio_message(
                    "voice.audio.cancel",
                    transport.endpoint_id,
                    false
                )
            )) {
                fail_voice_stream(transport);
            }
            continue;
        }

        const std::size_t batch_size = xStreamBufferReceive(
            transport.voice_audio_stream,
            audio_batch,
            kMaximumAudioBatchBytes,
            pdMS_TO_TICKS(20)
        );
        if (batch_size > 0) {
            const bool sent = esp_websocket_client_send_bin(
                transport.client,
                reinterpret_cast<const char *>(audio_batch),
                static_cast<int>(batch_size),
                pdMS_TO_TICKS(5000)
            ) == static_cast<int>(batch_size);
            if (!sent) {
                ESP_LOGW(kTag, "Could not send buffered voice audio data");
                xStreamBufferReset(transport.voice_audio_stream);
                fail_voice_stream(transport);
            }
            continue;
        }

        if (
            transport.voice_end_pending.exchange(false)
            && xStreamBufferBytesAvailable(transport.voice_audio_stream) == 0
        ) {
            if (!send_text(
                transport.client,
                voice_audio_message(
                    "voice.audio.end",
                    transport.endpoint_id,
                    false
                )
            )) {
                fail_voice_stream(transport);
            }
        }
    }
}

}  // namespace

StartResult start(const roomhub::config::EndpointConfig &config)
{
    StartResult result;
    context.events = xEventGroupCreate();
    context.voice_response_mutex = xSemaphoreCreateMutex();
    context.firmware_status_mutex = xSemaphoreCreateMutex();
    context.voice_audio_stream_state = static_cast<StaticStreamBuffer_t *>(
        heap_caps_calloc(1, sizeof(StaticStreamBuffer_t), MALLOC_CAP_INTERNAL)
    );
    context.voice_audio_storage = static_cast<std::uint8_t *>(heap_caps_malloc(
        kAudioStreamBufferBytes,
        MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT
    ));
    if (
        context.voice_audio_stream_state != nullptr
        && context.voice_audio_storage != nullptr
    ) {
        context.voice_audio_stream = xStreamBufferCreateStatic(
            kAudioStreamBufferBytes,
            kMaximumAudioFrameBytes,
            context.voice_audio_storage,
            context.voice_audio_stream_state
        );
    }
    context.endpoint_id = config.endpoint_id;
    context.roomhub_url = config.roomhub_url;
    roomhub::board::set_tab5_audio_event_callback(send_audio_playback_event);
    context.registration = registration_message(
        context.endpoint_id,
        roomhub::config::EndpointConfigStore().load_area_id()
    );
    if (
        context.events == nullptr
        || context.voice_response_mutex == nullptr
        || context.firmware_status_mutex == nullptr
        || context.voice_audio_stream == nullptr
        || context.registration.empty()
    ) {
        ESP_LOGE(kTag, "Could not allocate RoomHub transport state");
        return result;
    }

    const std::string url = websocket_url(config.roomhub_url);
    esp_websocket_client_config_t websocket_config{};
    websocket_config.uri = url.c_str();
    websocket_config.crt_bundle_attach = esp_crt_bundle_attach;
    websocket_config.network_timeout_ms = 10000;
    websocket_config.reconnect_timeout_ms = 1000;
    websocket_config.ping_interval_sec = 5;
    websocket_config.pingpong_timeout_sec = 5;
    websocket_config.buffer_size = 8192;
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
    roomhub::board::show_tab5_roomhub_connecting();
    if (xTaskCreate(
        heartbeat_task,
        "roomhub_heartbeat",
        4096,
        &context,
        4,
        nullptr
    ) != pdPASS) {
        ESP_LOGW(kTag, "Could not start RoomHub connection maintenance");
    }
    if (xTaskCreate(
        voice_sender_task,
        "roomhub_voice_tx",
        4096,
        &context,
        5,
        nullptr
    ) != pdPASS) {
        ESP_LOGE(kTag, "Could not start RoomHub voice audio sender");
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

    return result;
}

bool start_voice_audio()
{
    if (!voice_transport_ready()) {
        ESP_LOGW(kTag, "Cannot start voice audio while RoomHub is unavailable");
        return false;
    }
    context.network_audio_allowed = false;
    context.voice_end_pending = false;
    context.voice_cancel_pending = false;
    xStreamBufferReset(context.voice_audio_stream);
    xEventGroupClearBits(
        context.events,
        kVoiceAudioReady | kVoiceResponseReady | kVoiceFailed
    );
    if (xSemaphoreTake(context.voice_response_mutex, pdMS_TO_TICKS(100))
        == pdTRUE) {
        context.voice_response = {};
        xSemaphoreGive(context.voice_response_mutex);
    }
    const std::string message = voice_audio_message(
        "voice.audio.start",
        context.endpoint_id,
        true
    );
    if (!send_text(context.client, message)) {
        return false;
    }
    const EventBits_t state = xEventGroupWaitBits(
        context.events,
        kVoiceAudioReady | kVoiceFailed,
        pdFALSE,
        pdFALSE,
        pdMS_TO_TICKS(5000)
    );
    return (state & kVoiceAudioReady) != 0;
}

bool send_voice_audio(const std::int16_t *samples, std::size_t byte_count)
{
    if (
        samples == nullptr
        || byte_count == 0
        || byte_count > kMaximumAudioFrameBytes
        || !voice_transport_ready()
    ) {
        ESP_LOGW(
            kTag,
            "Cannot queue voice frame: bytes=%u transport_ready=%s",
            static_cast<unsigned>(byte_count),
            voice_transport_ready() ? "yes" : "no"
        );
        return false;
    }
    const EventBits_t state = xEventGroupGetBits(context.events);
    if ((state & kVoiceAudioReady) == 0 || !context.network_audio_allowed) {
        ESP_LOGW(kTag, "Cannot queue voice frame outside an active stream");
        return false;
    }
    const std::size_t queued = xStreamBufferSend(
        context.voice_audio_stream,
        samples,
        byte_count,
        0
    );
    if (queued != byte_count) {
        ESP_LOGW(
            kTag,
            "Voice audio buffer is full: %u bytes pending",
            static_cast<unsigned>(xStreamBufferBytesAvailable(
                context.voice_audio_stream
            ))
        );
        return false;
    }
    return true;
}

bool end_voice_audio()
{
    context.network_audio_allowed = false;
    xEventGroupClearBits(context.events, kVoiceAudioReady);
    context.voice_end_pending = true;
    return true;
}

bool cancel_voice_audio()
{
    context.network_audio_allowed = false;
    xEventGroupClearBits(context.events, kVoiceAudioReady);
    context.voice_cancel_pending = true;
    return context.voice_audio_stream != nullptr && voice_transport_ready();
}

VoiceResponseState voice_response_state()
{
    if (context.events == nullptr) {
        return VoiceResponseState::failed;
    }
    const EventBits_t state = xEventGroupGetBits(context.events);
    if ((state & kVoiceFailed) != 0) {
        return VoiceResponseState::failed;
    }
    if ((state & kVoiceResponseReady) != 0) {
        return VoiceResponseState::ready;
    }
    return VoiceResponseState::pending;
}

VoiceResponse take_voice_response()
{
    VoiceResponse response;
    if (context.voice_response_mutex != nullptr
        && xSemaphoreTake(context.voice_response_mutex, pdMS_TO_TICKS(100))
            == pdTRUE) {
        response = context.voice_response;
        context.voice_response = {};
        xSemaphoreGive(context.voice_response_mutex);
    }
    return response;
}

}  // namespace roomhub::transport
