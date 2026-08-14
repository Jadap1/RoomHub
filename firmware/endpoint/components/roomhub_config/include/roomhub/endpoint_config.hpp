#pragma once

#include <cstddef>
#include <string>

#include "esp_err.h"

namespace roomhub::config {

inline constexpr std::size_t kMaximumEndpointIdLength = 64;
inline constexpr std::size_t kMaximumRoomHubUrlLength = 256;
inline constexpr std::size_t kMaximumWifiSsidLength = 32;
inline constexpr std::size_t kMaximumWifiPasswordLength = 64;
inline constexpr std::size_t kMaximumDeviceTokenLength = 128;
inline constexpr std::size_t kMaximumAreaIdLength = 64;
inline constexpr char kDefaultRoomHubUrl[] = "http://homeassistant.local:8000";

struct EndpointConfig {
    std::string endpoint_id;
    std::string roomhub_url;
    std::string wifi_ssid;
    std::string wifi_password;
    std::string device_token;
};

enum class LoadStatus {
    ready,
    not_provisioned,
    invalid,
    storage_error,
};

struct LoadResult {
    LoadStatus status = LoadStatus::storage_error;
    esp_err_t error = ESP_FAIL;
    EndpointConfig config;
};

esp_err_t initialize_storage();
bool is_valid(const EndpointConfig &config);

class EndpointConfigStore {
public:
    LoadResult load() const;
    esp_err_t save(const EndpointConfig &config) const;
    esp_err_t clear() const;
    std::string load_area_id() const;
    esp_err_t save_area_id(const std::string &area_id) const;
    bool load_microphone_muted() const;
    esp_err_t save_microphone_muted(bool muted) const;
};

}  // namespace roomhub::config
