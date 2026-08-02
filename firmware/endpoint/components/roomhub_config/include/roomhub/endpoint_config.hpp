#pragma once

#include <string>

#include "esp_err.h"

namespace roomhub::config {

struct EndpointConfig {
    std::string endpoint_id;
    std::string roomhub_url;
    std::string wifi_ssid;
    std::string wifi_password;
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
};

}  // namespace roomhub::config
