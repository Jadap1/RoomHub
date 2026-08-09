#include "tab5_bringup.hpp"

#include "bsp/m5stack_tab5.h"
#include "esp_codec_dev.h"
#include "esp_log.h"
#include "lvgl.h"

namespace roomhub::board {
namespace {

constexpr char kTag[] = "roomhub_tab5";

esp_codec_dev_handle_t microphone = nullptr;
esp_codec_dev_handle_t speaker = nullptr;
lv_obj_t *wake_word_status = nullptr;
lv_obj_t *wireless_status = nullptr;

void set_wake_word_status(const char *text, uint32_t color)
{
    if (wake_word_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(wake_word_status, text);
    lv_obj_set_style_text_color(wake_word_status, lv_color_hex(color), 0);
    bsp_display_unlock();
}

void on_touch(lv_event_t *event)
{
    auto *label = static_cast<lv_obj_t *>(lv_event_get_user_data(event));
    lv_label_set_text(label, "Touch detected");
    ESP_LOGI(kTag, "Touch input confirmed");
}

void create_status_screen(
    lv_display_t *display,
    const Tab5BringUpResult &result,
    bool endpoint_provisioned
)
{
    lv_obj_t *screen = lv_display_get_screen_active(display);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x101820), 0);
    lv_obj_set_style_text_color(screen, lv_color_hex(0xf2f5f7), 0);

    lv_obj_t *panel = lv_obj_create(screen);
    lv_obj_set_size(panel, lv_pct(88), lv_pct(82));
    lv_obj_center(panel);
    lv_obj_set_style_bg_color(panel, lv_color_hex(0x172733), 0);
    lv_obj_set_style_border_color(panel, lv_color_hex(0x2bcbba), 0);
    lv_obj_set_style_border_width(panel, 3, 0);
    lv_obj_set_style_radius(panel, 24, 0);
    lv_obj_set_style_pad_all(panel, 36, 0);
    lv_obj_set_flex_flow(panel, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        panel,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );

    lv_obj_t *title = lv_label_create(panel);
    lv_label_set_text(title, "RoomHub");
    lv_obj_set_style_text_color(title, lv_color_hex(0x2bcbba), 0);
    lv_obj_set_style_pad_bottom(title, 18, 0);

    lv_obj_t *subtitle = lv_label_create(panel);
    lv_label_set_text(subtitle, "M5Stack Tab5 hardware bring-up");
    lv_obj_set_style_pad_bottom(subtitle, 28, 0);

    lv_obj_t *status = lv_label_create(panel);
    lv_label_set_text_fmt(
        status,
        "Firmware boot: ready\n"
        "Display: ready\n"
        "Touch controller: %s\n"
        "Microphone codec: %s\n"
        "Speaker codec: %s\n"
        "Configuration: %s\n"
        "Network audio: disabled",
        result.touch_ready ? "ready" : "failed",
        result.microphone_ready ? "ready" : "failed",
        result.speaker_ready ? "ready" : "failed",
        endpoint_provisioned ? "ready" : "provisioning required"
    );
    lv_obj_set_style_text_line_space(status, 12, 0);
    lv_obj_set_style_pad_bottom(status, 18, 0);

    wireless_status = lv_label_create(panel);
    lv_label_set_text(wireless_status, "Wireless: checking ESP32-C6");
    lv_obj_set_style_text_color(wireless_status, lv_color_hex(0xf6b93b), 0);
    lv_obj_set_style_pad_bottom(wireless_status, 12, 0);

    wake_word_status = lv_label_create(panel);
    lv_label_set_text(wake_word_status, "Wake word: starting");
    lv_obj_set_style_text_color(wake_word_status, lv_color_hex(0xf6b93b), 0);
    lv_obj_set_style_pad_bottom(wake_word_status, 18, 0);

    lv_obj_t *button = lv_button_create(panel);
    lv_obj_set_size(button, 360, 78);
    lv_obj_set_style_bg_color(button, lv_color_hex(0x2bcbba), 0);
    lv_obj_t *button_label = lv_label_create(button);
    lv_label_set_text(button_label, "Touch to test");
    lv_obj_center(button_label);
    if (result.touch_ready) {
        lv_obj_add_event_cb(button, on_touch, LV_EVENT_CLICKED, button_label);
    } else {
        lv_obj_add_state(button, LV_STATE_DISABLED);
    }
}

}  // namespace

Tab5BringUpResult initialize_tab5(bool endpoint_provisioned)
{
    Tab5BringUpResult result;

    microphone = bsp_audio_codec_microphone_init();
    result.microphone_ready = microphone != nullptr;
    result.microphone = microphone;
    speaker = bsp_audio_codec_speaker_init();
    result.speaker_ready = speaker != nullptr;
    result.speaker = speaker;
    if (result.speaker_ready) {
        const esp_err_t disable_result = bsp_feature_enable(
            BSP_FEATURE_SPEAKER,
            false
        );
        if (disable_result != ESP_OK) {
            ESP_LOGW(
                kTag,
                "Could not disable the idle speaker amplifier: %s",
                esp_err_to_name(disable_result)
            );
        }
    }

    lv_display_t *display = bsp_display_start();
    result.display_ready = display != nullptr;
    result.touch_ready = (
        result.display_ready && bsp_display_get_input_dev() != nullptr
    );
    if (!result.display_ready) {
        ESP_LOGE(kTag, "Display initialization failed");
        return result;
    }

    if (!bsp_display_lock(0)) {
        ESP_LOGE(kTag, "Could not lock the display for initial rendering");
        result.display_ready = false;
        return result;
    }
    bsp_display_rotate(display, LV_DISPLAY_ROTATION_90);
    create_status_screen(display, result, endpoint_provisioned);
    bsp_display_unlock();

    const esp_err_t brightness_result = bsp_display_brightness_set(35);
    if (brightness_result != ESP_OK) {
        ESP_LOGW(
            kTag,
            "Could not set display brightness: %s",
            esp_err_to_name(brightness_result)
        );
    }
    return result;
}

void show_tab5_wake_word_listening()
{
    set_wake_word_status("Wake word: listening for Jarvis", 0x2bcbba);
}

void show_tab5_wake_word_detected()
{
    set_wake_word_status("Wake word: Jarvis detected", 0x78e08f);
}

void show_tab5_wireless_scan(unsigned int network_count)
{
    if (wireless_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text_fmt(
        wireless_status,
        "Wireless: ESP32-C6 ready (%u networks found)",
        network_count
    );
    lv_obj_set_style_text_color(wireless_status, lv_color_hex(0x2bcbba), 0);
    bsp_display_unlock();
}

void show_tab5_wireless_connected()
{
    if (wireless_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(wireless_status, "Wireless: connected through ESP32-C6");
    lv_obj_set_style_text_color(wireless_status, lv_color_hex(0x2bcbba), 0);
    bsp_display_unlock();
}

void show_tab5_wireless_failed()
{
    if (wireless_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(wireless_status, "Wireless: ESP32-C6 failed");
    lv_obj_set_style_text_color(wireless_status, lv_color_hex(0xe55039), 0);
    bsp_display_unlock();
}

}  // namespace roomhub::board
