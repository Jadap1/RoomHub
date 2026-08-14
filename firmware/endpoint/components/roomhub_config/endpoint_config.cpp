#include "roomhub/endpoint_config.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include "nvs.h"
#include "nvs_flash.h"

namespace roomhub::config {
namespace {

constexpr char kNamespace[] = "roomhub";
constexpr char kEndpointIdKey[] = "endpoint_id";
constexpr char kRoomHubUrlKey[] = "roomhub_url";
constexpr char kWifiSsidKey[] = "wifi_ssid";
constexpr char kWifiPasswordKey[] = "wifi_password";
constexpr char kAreaIdKey[] = "area_id";
constexpr char kMicrophoneMutedKey[] = "mic_muted";

bool has_prefix(const std::string &value, const char *prefix)
{
    return value.rfind(prefix, 0) == 0;
}

esp_err_t read_string(
    nvs_handle_t handle,
    const char *key,
    std::size_t maximum_length,
    std::string &value
)
{
    std::size_t required_size = 0;
    esp_err_t result = nvs_get_str(handle, key, nullptr, &required_size);
    if (result != ESP_OK) {
        return result;
    }
    if (required_size == 0 || required_size > maximum_length + 1) {
        return ESP_ERR_NVS_VALUE_TOO_LONG;
    }

    std::vector<char> buffer(required_size);
    result = nvs_get_str(handle, key, buffer.data(), &required_size);
    if (result == ESP_OK) {
        value.assign(buffer.data());
    }
    return result;
}

esp_err_t read_config(nvs_handle_t handle, EndpointConfig &config)
{
    esp_err_t result = read_string(
        handle,
        kEndpointIdKey,
        kMaximumEndpointIdLength,
        config.endpoint_id
    );
    if (result != ESP_OK) {
        return result;
    }
    result = read_string(
        handle,
        kRoomHubUrlKey,
        kMaximumRoomHubUrlLength,
        config.roomhub_url
    );
    if (result != ESP_OK) {
        return result;
    }
    result = read_string(
        handle,
        kWifiSsidKey,
        kMaximumWifiSsidLength,
        config.wifi_ssid
    );
    if (result != ESP_OK) {
        return result;
    }
    return read_string(
        handle,
        kWifiPasswordKey,
        kMaximumWifiPasswordLength,
        config.wifi_password
    );
}

}  // namespace

esp_err_t initialize_storage()
{
    // Do not erase automatically: configuration may contain the only copy of
    // credentials. Recovery and migration must be an explicit provisioning act.
    return nvs_flash_init();
}

bool is_valid(const EndpointConfig &config)
{
    const bool valid_url = (
        has_prefix(config.roomhub_url, "http://")
        || has_prefix(config.roomhub_url, "https://")
    );
    return !config.endpoint_id.empty()
        && config.endpoint_id.size() <= kMaximumEndpointIdLength
        && valid_url
        && config.roomhub_url.size() <= kMaximumRoomHubUrlLength
        && !config.wifi_ssid.empty()
        && config.wifi_ssid.size() <= kMaximumWifiSsidLength
        && config.wifi_password.size() <= kMaximumWifiPasswordLength;
}

LoadResult EndpointConfigStore::load() const
{
    nvs_handle_t handle = 0;
    const esp_err_t open_result = nvs_open(
        kNamespace,
        NVS_READONLY,
        &handle
    );
    if (open_result == ESP_ERR_NVS_NOT_FOUND) {
        return {LoadStatus::not_provisioned, ESP_OK, {}};
    }
    if (open_result != ESP_OK) {
        return {LoadStatus::storage_error, open_result, {}};
    }

    EndpointConfig config;
    const esp_err_t read_result = read_config(handle, config);
    nvs_close(handle);

    if (read_result == ESP_ERR_NVS_NOT_FOUND) {
        return {LoadStatus::not_provisioned, ESP_OK, {}};
    }
    if (read_result == ESP_ERR_NVS_VALUE_TOO_LONG) {
        return {LoadStatus::invalid, read_result, {}};
    }
    if (read_result != ESP_OK) {
        return {LoadStatus::storage_error, read_result, {}};
    }
    if (!is_valid(config)) {
        return {LoadStatus::invalid, ESP_ERR_INVALID_ARG, {}};
    }
    return {LoadStatus::ready, ESP_OK, std::move(config)};
}

esp_err_t EndpointConfigStore::save(const EndpointConfig &config) const
{
    if (!is_valid(config)) {
        return ESP_ERR_INVALID_ARG;
    }

    nvs_handle_t handle = 0;
    esp_err_t result = nvs_open(kNamespace, NVS_READWRITE, &handle);
    if (result != ESP_OK) {
        return result;
    }

    result = nvs_set_str(handle, kEndpointIdKey, config.endpoint_id.c_str());
    if (result == ESP_OK) {
        result = nvs_set_str(handle, kRoomHubUrlKey, config.roomhub_url.c_str());
    }
    if (result == ESP_OK) {
        result = nvs_set_str(handle, kWifiSsidKey, config.wifi_ssid.c_str());
    }
    if (result == ESP_OK) {
        result = nvs_set_str(
            handle,
            kWifiPasswordKey,
            config.wifi_password.c_str()
        );
    }
    if (result == ESP_OK) {
        result = nvs_commit(handle);
    }
    nvs_close(handle);
    return result;
}

esp_err_t EndpointConfigStore::clear() const
{
    nvs_handle_t handle = 0;
    esp_err_t result = nvs_open(kNamespace, NVS_READWRITE, &handle);
    if (result == ESP_ERR_NVS_NOT_FOUND) {
        return ESP_OK;
    }
    if (result != ESP_OK) {
        return result;
    }

    result = nvs_erase_all(handle);
    if (result == ESP_OK) {
        result = nvs_commit(handle);
    }
    nvs_close(handle);
    return result;
}

std::string EndpointConfigStore::load_area_id() const
{
    nvs_handle_t handle = 0;
    if (nvs_open(kNamespace, NVS_READONLY, &handle) != ESP_OK) {
        return {};
    }
    std::string area_id;
    const esp_err_t result = read_string(
        handle, kAreaIdKey, kMaximumAreaIdLength, area_id
    );
    nvs_close(handle);
    return result == ESP_OK ? area_id : std::string{};
}

esp_err_t EndpointConfigStore::save_area_id(const std::string &area_id) const
{
    if (area_id.empty() || area_id.size() > kMaximumAreaIdLength) {
        return ESP_ERR_INVALID_ARG;
    }
    nvs_handle_t handle = 0;
    esp_err_t result = nvs_open(kNamespace, NVS_READWRITE, &handle);
    if (result == ESP_OK) {
        result = nvs_set_str(handle, kAreaIdKey, area_id.c_str());
    }
    if (result == ESP_OK) {
        result = nvs_commit(handle);
    }
    if (handle != 0) {
        nvs_close(handle);
    }
    return result;
}

bool EndpointConfigStore::load_microphone_muted() const
{
    nvs_handle_t handle = 0;
    if (nvs_open(kNamespace, NVS_READONLY, &handle) != ESP_OK) return false;
    std::uint8_t value = 0;
    const esp_err_t result = nvs_get_u8(handle, kMicrophoneMutedKey, &value);
    nvs_close(handle);
    return result == ESP_OK && value != 0;
}

esp_err_t EndpointConfigStore::save_microphone_muted(bool muted) const
{
    nvs_handle_t handle = 0;
    esp_err_t result = nvs_open(kNamespace, NVS_READWRITE, &handle);
    if (result == ESP_OK) result = nvs_set_u8(handle, kMicrophoneMutedKey, muted ? 1 : 0);
    if (result == ESP_OK) result = nvs_commit(handle);
    if (handle != 0) nvs_close(handle);
    return result;
}

}  // namespace roomhub::config
