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
#include "roomhub/version_policy.hpp"
#include "tab5_bringup.hpp"

namespace roomhub::ota {
namespace {

constexpr char kTag[] = "roomhub_ota";
constexpr std::size_t kBufferBytes = 8192;
std::atomic_bool update_active{false};
std::atomic_bool update_network_busy{false};

struct UpdateRequest {
    std::string request_id;
    std::string url;
    std::string version;
    std::size_t size;
    std::uint8_t sha256[32];
    StatusCallback status_callback;
};

void report(const UpdateRequest &request, const char *status, unsigned int progress, const char *reason = nullptr)
{
    if (request.status_callback != nullptr) {
        request.status_callback(
            request.request_id, request.version, status, progress, reason
        );
    }
}

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
    const esp_err_t open_result = client == nullptr
        ? ESP_ERR_NO_MEM : esp_http_client_open(client, 0);
    if (open_result != ESP_OK) {
        ESP_LOGE(kTag, "Firmware HTTP open failed: %s", esp_err_to_name(open_result));
        if (client != nullptr) esp_http_client_cleanup(client);
        return false;
    }
    const int content_length = esp_http_client_fetch_headers(client);
    if (esp_http_client_get_status_code(client) != 200
        || (content_length >= 0
            && static_cast<std::size_t>(content_length) != request.size)) {
        ESP_LOGE(
            kTag,
            "Firmware HTTP response invalid: status=%d length=%d expected=%u",
            esp_http_client_get_status_code(client),
            content_length,
            static_cast<unsigned int>(request.size)
        );
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return false;
    }

    const esp_partition_t *partition = esp_ota_get_next_update_partition(nullptr);
    esp_ota_handle_t ota_handle = 0;
    const esp_err_t begin_result = partition == nullptr
        ? ESP_ERR_NOT_FOUND : esp_ota_begin(partition, request.size, &ota_handle);
    if (begin_result != ESP_OK) {
        ESP_LOGE(kTag, "Firmware OTA begin failed: %s", esp_err_to_name(begin_result));
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
    unsigned int last_reported_progress = 0;
    while (okay && received < request.size) {
        const int count = esp_http_client_read(
            client,
            reinterpret_cast<char *>(buffer.get()),
            kBufferBytes
        );
        if (count <= 0) {
            ESP_LOGE(
                kTag,
                "Firmware HTTP read ended early: result=%d received=%u expected=%u complete=%s",
                count,
                static_cast<unsigned int>(received),
                static_cast<unsigned int>(request.size),
                esp_http_client_is_complete_data_received(client) ? "yes" : "no"
            );
            okay = false;
            break;
        }
        received += static_cast<std::size_t>(count);
        const esp_err_t write_result = received > request.size
            ? ESP_ERR_INVALID_SIZE : esp_ota_write(ota_handle, buffer.get(), count);
        if (write_result != ESP_OK) {
            ESP_LOGE(kTag, "Firmware OTA write failed: %s", esp_err_to_name(write_result));
            okay = false;
            break;
        }
        mbedtls_sha256_update(&sha, buffer.get(), count);
        const unsigned int progress = static_cast<unsigned int>((received * 100) / request.size);
        roomhub::board::show_tab5_firmware_updating(progress);
        if (progress == 100 || progress >= last_reported_progress + 5) {
            report(request, "downloading", progress);
            last_reported_progress = progress;
        }
    }
    std::uint8_t digest[32]{};
    mbedtls_sha256_finish(&sha, digest);
    mbedtls_sha256_free(&sha);
    esp_http_client_close(client);
    esp_http_client_cleanup(client);

    okay = okay && received == request.size
        && std::memcmp(digest, request.sha256, sizeof(digest)) == 0;
    if (!okay) {
        ESP_LOGE(
            kTag,
            "Firmware integrity check failed: received=%u expected=%u",
            static_cast<unsigned int>(received),
            static_cast<unsigned int>(request.size)
        );
        esp_ota_abort(ota_handle);
        return false;
    }
    const esp_err_t end_result = esp_ota_end(ota_handle);
    if (end_result != ESP_OK) {
        ESP_LOGE(kTag, "Firmware signature verification failed: %s", esp_err_to_name(end_result));
        return false;
    }
    esp_app_desc_t candidate{};
    if (esp_ota_get_partition_description(partition, &candidate) != ESP_OK
        || request.version != candidate.version
        || !roomhub::firmware::is_upgrade(
            esp_app_get_description()->version,
            candidate.version
        )
        || esp_ota_set_boot_partition(partition) != ESP_OK) {
        ESP_LOGE(kTag, "Firmware candidate version or boot selection rejected");
        return false;
    }
    return true;
}

void update_task(void *argument)
{
    std::unique_ptr<UpdateRequest> request(static_cast<UpdateRequest *>(argument));
    // Give the transport task time to acknowledge the command before the C6
    // network link is dedicated to the firmware HTTP stream.
    vTaskDelay(pdMS_TO_TICKS(750));
    ESP_LOGI(kTag, "Installing endpoint firmware %s", request->version.c_str());
    update_network_busy = true;
    const bool installed = install(*request);
    update_network_busy = false;
    if (installed) {
        report(*request, "restarting", 100);
        roomhub::board::show_tab5_firmware_restarting();
        ESP_LOGI(kTag, "Firmware verified; restarting into %s", request->version.c_str());
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_restart();
    }
    ESP_LOGE(kTag, "Firmware update rejected; running image preserved");
    report(*request, "failed", 0, "install_failed");
    roomhub::board::show_tab5_firmware_failed();
    update_active = false;
    vTaskDelete(nullptr);
}

}  // namespace

bool start(
    const std::string &request_id,
    const std::string &url,
    const std::string &version,
    std::size_t expected_size,
    const std::string &expected_sha256,
    StatusCallback status_callback
)
{
    if (update_active.exchange(true) || expected_size == 0
        || !roomhub::firmware::is_upgrade(
            esp_app_get_description()->version,
            version
        )) {
        return false;
    }
    std::unique_ptr<UpdateRequest> request(new (std::nothrow) UpdateRequest{
        .request_id = request_id,
        .url = url,
        .version = version,
        .size = expected_size,
        .sha256 = {},
        .status_callback = status_callback,
    });
    if (request == nullptr || !decode_sha256(expected_sha256, request->sha256)) {
        update_active = false;
        return false;
    }
    UpdateRequest *task_request = request.release();
    report(*task_request, "accepted", 0);
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

bool network_busy()
{
    return update_network_busy.load();
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
