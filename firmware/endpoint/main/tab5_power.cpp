#include "tab5_power.hpp"

#include "bsp/m5stack_tab5.h"
#include "esp_log.h"

namespace roomhub::board {
namespace {

constexpr char kTag[] = "roomhub_power";
constexpr uint32_t kChargeEnable = IO_EXPANDER_PIN_NUM_7;
constexpr uint32_t kChargeStatus = IO_EXPANDER_PIN_NUM_6;

}  // namespace

bool initialize_tab5_charger()
{
    esp_io_expander_handle_t expander = bsp_io_expander1_init();
    if (expander == nullptr) {
        ESP_LOGE(kTag, "Could not initialise the Tab5 power IO expander");
        return false;
    }
    esp_err_t result = esp_io_expander_set_dir(
        expander, kChargeEnable, IO_EXPANDER_OUTPUT
    );
    if (result == ESP_OK) {
        result = esp_io_expander_set_output_mode(
            expander, kChargeEnable, IO_EXPANDER_OUTPUT_MODE_PUSH_PULL
        );
    }
    if (result == ESP_OK) {
        result = esp_io_expander_set_level(expander, kChargeEnable, 1);
    }
    if (result == ESP_OK) {
        result = esp_io_expander_set_dir(
            expander, kChargeStatus, IO_EXPANDER_INPUT
        );
    }
    if (result != ESP_OK) {
        ESP_LOGE(kTag, "Could not enable Tab5 battery charging: %s", esp_err_to_name(result));
        return false;
    }

    uint32_t status = 0;
    if (esp_io_expander_get_level(expander, kChargeStatus, &status) == ESP_OK) {
        ESP_LOGI(
            kTag,
            "Battery charging enabled; charger status pin=%s",
            (status & kChargeStatus) != 0 ? "high" : "low"
        );
    } else {
        ESP_LOGI(kTag, "Battery charging enabled");
    }
    return true;
}

}  // namespace roomhub::board
