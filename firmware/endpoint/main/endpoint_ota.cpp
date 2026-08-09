#include "endpoint_ota.hpp"

#include <atomic>
#include <cstdint>
#include <cstring>
#include <memory>
#include <string>

#include "esp_app_desc.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "tab5_bringup.hpp"

namespace roomhub::ota {
namespace {

constexpr char kTag[] = "roomhub_ota";
constexpr std::size_t kBufferBytes = 8192;
std::atomic_bool update_active{false};

struct UpdateRequest {
    std::string url;
    std::string version;
    std::size_t size;
    std::uint8_t sha256[32];
};

bool decode_sha256(const std::string &encoded, std::uint8_t output[32])
{
    if (encoded.size() != 64) {
        return false;
    }
    for (std::size_t index = 0; index < 32; ++index) {
        const auto nibble = [](char value) -> int {
            if (value >= '0' && value <= '9') return value - '0';
            if (value >= 'a' && value <= 'f') return value - 'a' + 10;
            if (value >= 'A' && value <= 'F') return value - 'A' + 10;
            return -1;
        };
        const int high = nibble(encoded[index * 2]);
        const int low = nibble(encoded[index * 2 + 1]);
        if (high < 0 || low < 0) {
            return false;
        }
        output[index] = static_cast<std::uint8_t>((high << 4) | low);
    }
    return true;
}

bool install(const UpdateRequest &request)
{
    esp_http_client_config_t config{};
    config.url = request.url.c_str();
    config.timeout_ms = 15000;
    config.buffer_size = kBufferBytes;
    config.crt_bundle_attach = esp_crt_bundle_attach;
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (client == nullptr || esp_http_client_open(client, 0) != ESP_OK) {
        if (client != nullptr) esp_http_client_cleanup(client);
        return false;
    }
    const int content_length = esp_http_client_fetch_headers(client);
    if (esp_http_client_get_status_code(client) != 200
        || (content_length >= 0
            && static_cast<std::size_t>(content_length) != request.size)) {
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return false;
    }

    const esp_partition_t *partition = esp_ota_get_next_update_partition(nullptr);
    esp_ota_handle_t ota_handle = 0;
    if (partition == nullptr
        || esp_ota_begin(partition, request.size, &ota_handle) != ESP_OK) {
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return false;
    }

    std::unique_ptr<std::uint8_t[]> buffer(new (std::nothrow) std::uint8_t[kBufferBytes]);
    mbedtls_sha256_context sha{};
    mbedtls_sha256_init(&sha);
    mbedtls_sha256_starts(&sha, 0);
    std::size_t received = 0;
    bool okay = buffer != nullptr;
    while (okay && received < request.size) {
        const int count = esp_http_client_read(
            client,
            reinterpret_cast<char *>(buffer.get()),
            kBufferBytes
        );
        if (count <= 0) {
            okay = false;
            break;
        }
        received += static_cast<std::size_t>(count);
        if (received > request.size
            || esp_ota_write(ota_handle, buffer.get(), count) != ESP_OK) {
            okay = false;
            break;
        }
        mbedtls_sha256_update(&sha, buffer.get(), count);
        roomhub::board::show_tab5_firmware_updating(
            static_cast<unsigned int>((received * 100) / request.size)
        );
    }
    std::uint8_t digest[32]{};
    mbedtls_sha256_finish(&sha, digest);
    mbedtls_sha256_free(&sha);
    esp_http_client_close(client);
    esp_http_client_cleanup(client);

    okay = okay && received == request.size
        && std::memcmp(digest, request.sha256, sizeof(digest)) == 0;
    if (!okay) {
        esp_ota_abort(ota_handle);
        return false;
    }
    if (esp_ota_end(ota_handle) != ESP_OK
        || esp_ota_set_boot_partition(partition) != ESP_OK) {
        return false;
    }
    return true;
}

void update_task(void *argument)
{
    std::unique_ptr<UpdateRequest> request(static_cast<UpdateRequest *>(argument));
    ESP_LOGI(kTag, "Installing endpoint firmware %s", request->version.c_str());
    if (install(*request)) {
        roomhub::board::show_tab5_firmware_restarting();
        ESP_LOGI(kTag, "Firmware verified; restarting into %s", request->version.c_str());
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_restart();
    }
    ESP_LOGE(kTag, "Firmware update rejected; running image preserved");
    roomhub::board::show_tab5_firmware_failed();
    update_active = false;
    vTaskDelete(nullptr);
}

}  // namespace

bool start(
    const std::string &url,
    const std::string &version,
    std::size_t expected_size,
    const std::string &expected_sha256
)
{
    if (update_active.exchange(true) || expected_size == 0) {
        return false;
    }
    std::unique_ptr<UpdateRequest> request(new (std::nothrow) UpdateRequest{
        .url = url,
        .version = version,
        .size = expected_size,
    });
    if (request == nullptr || !decode_sha256(expected_sha256, request->sha256)) {
        update_active = false;
        return false;
    }
    UpdateRequest *task_request = request.release();
    if (xTaskCreate(update_task, "endpoint_ota", 8192, task_request, 5, nullptr) != pdPASS) {
        delete task_request;
        update_active = false;
        return false;
    }
    return true;
}

bool in_progress()
{
    return update_active.load();
}

void confirm_running_image()
{
    esp_ota_img_states_t state{};
    if (esp_ota_get_state_partition(esp_ota_get_running_partition(), &state) == ESP_OK
        && state == ESP_OTA_IMG_PENDING_VERIFY) {
        const esp_err_t result = esp_ota_mark_app_valid_cancel_rollback();
        ESP_LOGI(kTag, "OTA boot confirmation: %s", esp_err_to_name(result));
    }
}

}  // namespace roomhub::ota
