#include "usb_provisioning.hpp"

#include <algorithm>
#include <array>
#include <cstdio>
#include <string>

#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "roomhub/endpoint_config.hpp"

namespace roomhub::provisioning {
namespace {

constexpr char kStartRequest[] = "ROOMHUB_PROVISION 1";

template <std::size_t Size>
bool read_line(std::array<char, Size> &buffer, std::string &value)
{
    static_assert(Size > 2);

    while (true) {
        clearerr(stdin);
        if (fgets(buffer.data(), static_cast<int>(buffer.size()), stdin) == nullptr) {
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
        }

        const auto newline = std::find(
            buffer.begin(),
            buffer.end(),
            '\n'
        );
        if (newline == buffer.end()) {
            int character = 0;
            do {
                character = fgetc(stdin);
            } while (character != '\n' && character != EOF);
            return false;
        }

        auto end = newline;
        if (end != buffer.begin() && *(end - 1) == '\r') {
            --end;
        }
        value.assign(buffer.begin(), end);
        return true;
    }
}

template <std::size_t Size>
bool request_field(
    const char *field_name,
    std::array<char, Size> &buffer,
    std::string &value
)
{
    std::printf("ROOMHUB_FIELD %s\n", field_name);
    std::fflush(stdout);
    return read_line(buffer, value);
}

void clear_secret(std::string &secret)
{
    std::fill(secret.begin(), secret.end(), '\0');
    secret.clear();
    secret.shrink_to_fit();
}

}  // namespace

[[noreturn]] void run_usb_provisioning()
{
    roomhub::config::EndpointConfigStore store;

    std::printf("ROOMHUB_PROVISIONING_READY 1\n");
    std::fflush(stdout);

    while (true) {
        std::array<char, sizeof(kStartRequest) + 2> start_buffer{};
        std::string start_request;
        if (!read_line(start_buffer, start_request)
            || start_request != kStartRequest) {
            std::printf("ROOMHUB_RESULT unexpected_request\n");
            std::fflush(stdout);
            continue;
        }

        roomhub::config::EndpointConfig config;
        std::array<char, roomhub::config::kMaximumEndpointIdLength + 2>
            endpoint_id_buffer{};
        std::array<char, roomhub::config::kMaximumRoomHubUrlLength + 2>
            roomhub_url_buffer{};
        std::array<char, roomhub::config::kMaximumWifiSsidLength + 2>
            wifi_ssid_buffer{};
        std::array<char, roomhub::config::kMaximumWifiPasswordLength + 2>
            wifi_password_buffer{};
        std::array<char, roomhub::config::kMaximumDeviceTokenLength + 2>
            device_token_buffer{};

        const bool fields_read = request_field(
            "endpoint_id",
            endpoint_id_buffer,
            config.endpoint_id
        ) && request_field(
            "roomhub_url",
            roomhub_url_buffer,
            config.roomhub_url
        ) && request_field(
            "device_token",
            device_token_buffer,
            config.device_token
        ) && request_field(
            "wifi_ssid",
            wifi_ssid_buffer,
            config.wifi_ssid
        ) && request_field(
            "wifi_password",
            wifi_password_buffer,
            config.wifi_password
        );

        const bool config_valid = fields_read && roomhub::config::is_valid(config);
        const esp_err_t save_result = config_valid
            ? store.save(config)
            : ESP_ERR_INVALID_ARG;

        std::fill(wifi_password_buffer.begin(), wifi_password_buffer.end(), '\0');
        std::fill(device_token_buffer.begin(), device_token_buffer.end(), '\0');
        clear_secret(config.wifi_password);
        clear_secret(config.device_token);

        if (save_result != ESP_OK) {
            std::printf(
                "ROOMHUB_RESULT %s\n",
                config_valid ? "storage_error" : "invalid"
            );
            std::fflush(stdout);
            continue;
        }

        std::printf("ROOMHUB_RESULT saved\n");
        std::fflush(stdout);
        vTaskDelay(pdMS_TO_TICKS(250));
        esp_restart();
    }
}

}  // namespace roomhub::provisioning
