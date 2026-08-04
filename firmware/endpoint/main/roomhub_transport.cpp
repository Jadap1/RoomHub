#include "roomhub_transport.hpp"

#include <atomic>
#include <cstdint>
#include <string>

#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_websocket_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/stream_buffer.h"
#include "freertos/task.h"

namespace roomhub::transport {
namespace {

constexpr char kTag[] = "roomhub_transport";
constexpr EventBits_t kConnected = BIT0;
constexpr EventBits_t kRegistered = BIT1;
constexpr EventBits_t kFailed = BIT2;
constexpr EventBits_t kVoiceAudioReady = BIT3;
constexpr EventBits_t kVoiceResponseReady = BIT4;
constexpr EventBits_t kVoiceFailed = BIT5;
constexpr std::size_t kMaximumAudioFrameBytes = 1024;
constexpr std::size_t kMaximumAudioBatchBytes = 8192;
constexpr std::size_t kAudioStreamBufferBytes = 384000;

struct TransportContext {
    EventGroupHandle_t events = nullptr;
    esp_websocket_client_handle_t client = nullptr;
    std::string endpoint_id;
    std::string registration;
    std::atomic_bool network_audio_allowed{false};
    std::atomic_bool voice_end_pending{false};
    std::atomic_bool voice_cancel_pending{false};
    StreamBufferHandle_t voice_audio_stream = nullptr;
    StaticStreamBuffer_t *voice_audio_stream_state = nullptr;
    std::uint8_t *voice_audio_storage = nullptr;
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
            ESP_LOGI(kTag, "Endpoint registration accepted by RoomHub");
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
            xEventGroupSetBits(transport.events, kVoiceResponseReady);
            ESP_LOGI(kTag, "RoomHub completed the voice intent request");
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
        transport.network_audio_allowed = false;
        xEventGroupClearBits(transport.events, kVoiceAudioReady);
        xEventGroupSetBits(transport.events, kFailed | kVoiceFailed);
    }
}

void heartbeat_task(void *argument)
{
    auto &transport = *static_cast<TransportContext *>(argument);
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(10000));
        const EventBits_t state = xEventGroupGetBits(transport.events);
        if ((state & kConnected) != 0 && (state & kRegistered) == 0) {
            if (!send_text(transport.client, transport.registration)) {
                ESP_LOGW(kTag, "Could not resend endpoint registration");
            }
        } else if ((state & (kConnected | kRegistered))
                   == (kConnected | kRegistered)) {
            const std::string heartbeat = heartbeat_message(
                transport.endpoint_id,
                transport.network_audio_allowed.load()
            );
            if (!send_text(transport.client, heartbeat)) {
                ESP_LOGW(kTag, "Could not send RoomHub heartbeat");
            }
        }
    }
}

bool voice_transport_ready()
{
    if (context.events == nullptr || context.client == nullptr) {
        return false;
    }
    const EventBits_t state = xEventGroupGetBits(context.events);
    return (state & (kConnected | kRegistered)) == (kConnected | kRegistered);
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
    context.registration = registration_message(context.endpoint_id);
    if (
        context.events == nullptr
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

}  // namespace roomhub::transport
