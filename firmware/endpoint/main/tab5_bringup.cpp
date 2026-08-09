#include "tab5_bringup.hpp"

#include <string>
#include <vector>

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
lv_obj_t *roomhub_status = nullptr;
lv_obj_t *dashboard_area = nullptr;
lv_obj_t *dashboard_grid = nullptr;
std::vector<std::string> dashboard_entity_ids;
DashboardAction dashboard_action = nullptr;

void set_wake_word_status(const char *text, uint32_t color)
{
    if (wake_word_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(wake_word_status, text);
    lv_obj_set_style_text_color(wake_word_status, lv_color_hex(color), 0);
    bsp_display_unlock();
}

void on_dashboard_touch(lv_event_t *event)
{
    const char *entity_id = static_cast<const char *>(lv_event_get_user_data(event));
    if (dashboard_action != nullptr && entity_id != nullptr) {
        dashboard_action(entity_id);
        ESP_LOGI(kTag, "Dashboard action requested for %s", entity_id);
    }
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
    dashboard_area = subtitle;
    lv_label_set_text(dashboard_area, "Unassigned");
    lv_obj_set_style_pad_bottom(dashboard_area, 12, 0);

    lv_obj_t *status = lv_label_create(panel);
    lv_label_set_text_fmt(
        status,
        "Hardware: display ready, touch %s, microphone %s, speaker %s\n"
        "Configuration: %s",
        result.touch_ready ? "ready" : "failed",
        result.microphone_ready ? "ready" : "failed",
        result.speaker_ready ? "ready" : "failed",
        endpoint_provisioned ? "ready" : "provisioning required"
    );
    lv_obj_set_style_text_line_space(status, 6, 0);
    lv_obj_set_style_pad_bottom(status, 10, 0);

    wireless_status = lv_label_create(panel);
    lv_label_set_text(wireless_status, "Wireless: checking ESP32-C6");
    lv_obj_set_style_text_color(wireless_status, lv_color_hex(0xf6b93b), 0);
    lv_obj_set_style_pad_bottom(wireless_status, 12, 0);

    roomhub_status = lv_label_create(panel);
    lv_label_set_text(roomhub_status, "RoomHub: waiting for network");
    lv_obj_set_style_text_color(roomhub_status, lv_color_hex(0xf6b93b), 0);
    lv_obj_set_style_pad_bottom(roomhub_status, 12, 0);

    wake_word_status = lv_label_create(panel);
    lv_label_set_text(wake_word_status, "Wake word: starting");
    lv_obj_set_style_text_color(wake_word_status, lv_color_hex(0xf6b93b), 0);
    lv_obj_set_style_pad_bottom(wake_word_status, 10, 0);

    dashboard_grid = lv_obj_create(panel);
    lv_obj_set_width(dashboard_grid, lv_pct(100));
    lv_obj_set_flex_grow(dashboard_grid, 1);
    lv_obj_set_style_bg_opa(dashboard_grid, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(dashboard_grid, 0, 0);
    lv_obj_set_style_pad_all(dashboard_grid, 4, 0);
    lv_obj_set_flex_flow(dashboard_grid, LV_FLEX_FLOW_ROW_WRAP);
    lv_obj_set_flex_align(
        dashboard_grid,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START
    );
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

void show_tab5_wireless_retrying(unsigned int delay_seconds)
{
    if (wireless_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text_fmt(
        wireless_status,
        "Wireless: reconnecting in %u s",
        delay_seconds
    );
    lv_obj_set_style_text_color(wireless_status, lv_color_hex(0xf6b93b), 0);
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

void show_tab5_roomhub_connecting()
{
    if (roomhub_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(roomhub_status, "RoomHub: connecting");
    lv_obj_set_style_text_color(roomhub_status, lv_color_hex(0xf6b93b), 0);
    bsp_display_unlock();
}

void show_tab5_roomhub_retrying(unsigned int delay_seconds)
{
    if (roomhub_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text_fmt(
        roomhub_status,
        "RoomHub: reconnecting in %u s",
        delay_seconds
    );
    lv_obj_set_style_text_color(roomhub_status, lv_color_hex(0xf6b93b), 0);
    bsp_display_unlock();
}

void show_tab5_roomhub_registered()
{
    if (roomhub_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(roomhub_status, "RoomHub: connected and registered");
    lv_obj_set_style_text_color(roomhub_status, lv_color_hex(0x2bcbba), 0);
    bsp_display_unlock();
}

void show_tab5_firmware_updating(unsigned int percent)
{
    if (roomhub_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text_fmt(roomhub_status, "Firmware: updating %u%%", percent);
    lv_obj_set_style_text_color(roomhub_status, lv_color_hex(0xf6b93b), 0);
    bsp_display_unlock();
}

void show_tab5_firmware_failed()
{
    if (roomhub_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(roomhub_status, "Firmware: update rejected");
    lv_obj_set_style_text_color(roomhub_status, lv_color_hex(0xe55039), 0);
    bsp_display_unlock();
}

void show_tab5_firmware_restarting()
{
    if (roomhub_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(roomhub_status, "Firmware: verified; restarting");
    lv_obj_set_style_text_color(roomhub_status, lv_color_hex(0x2bcbba), 0);
    bsp_display_unlock();
}

void show_tab5_dashboard(
    const std::string &area_name,
    const std::vector<DashboardEntity> &entities,
    DashboardAction action
)
{
    if (dashboard_area == nullptr || dashboard_grid == nullptr || !bsp_display_lock(0)) {
        return;
    }
    dashboard_action = action;
    dashboard_entity_ids.clear();
    dashboard_entity_ids.reserve(entities.size());
    for (const auto &entity : entities) {
        dashboard_entity_ids.push_back(entity.entity_id);
    }
    lv_label_set_text(dashboard_area, area_name.c_str());
    lv_obj_clean(dashboard_grid);
    if (entities.empty()) {
        lv_obj_t *empty = lv_label_create(dashboard_grid);
        lv_label_set_text(empty, "No supported entities in this area");
    }
    for (std::size_t index = 0; index < entities.size() && index < 6; ++index) {
        const auto &entity = entities[index];
        lv_obj_t *button = lv_button_create(dashboard_grid);
        lv_obj_set_size(button, 300, 78);
        lv_obj_set_style_bg_color(
            button,
            lv_color_hex(entity.state == "on" ? 0x2bcbba : 0x34495e),
            0
        );
        if (!entity.available || !entity.actionable) {
            lv_obj_add_state(button, LV_STATE_DISABLED);
        }
        lv_obj_t *label = lv_label_create(button);
        lv_label_set_text_fmt(label, "%s\n%s", entity.name.c_str(), entity.state.c_str());
        lv_obj_center(label);
        if (entity.actionable) {
            lv_obj_add_event_cb(
                button,
                on_dashboard_touch,
                LV_EVENT_CLICKED,
                const_cast<char *>(dashboard_entity_ids[index].c_str())
            );
        }
    }
    bsp_display_unlock();
}

}  // namespace roomhub::board
