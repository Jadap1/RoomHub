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
std::vector<DashboardEntity> dashboard_entities;
DashboardAction dashboard_action = nullptr;
lv_obj_t *climate_overlay = nullptr;
std::string selected_climate_id;

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
    if (dashboard_action == nullptr || entity_id == nullptr) {
        return;
    }
    for (const auto &entity : dashboard_entities) {
        if (entity.entity_id == entity_id && entity.entity_type == "climate") {
            selected_climate_id = entity.entity_id;
            lv_obj_t *screen = lv_screen_active();
            climate_overlay = lv_obj_create(screen);
            lv_obj_set_size(climate_overlay, 620, 430);
            lv_obj_center(climate_overlay);
            lv_obj_set_style_bg_color(climate_overlay, lv_color_hex(0x172733), 0);
            lv_obj_set_style_border_color(climate_overlay, lv_color_hex(0x2bcbba), 0);
            lv_obj_set_style_border_width(climate_overlay, 2, 0);
            lv_obj_set_style_radius(climate_overlay, 22, 0);
            lv_obj_set_flex_flow(climate_overlay, LV_FLEX_FLOW_COLUMN);
            lv_obj_set_flex_align(
                climate_overlay,
                LV_FLEX_ALIGN_SPACE_EVENLY,
                LV_FLEX_ALIGN_CENTER,
                LV_FLEX_ALIGN_CENTER
            );
            lv_obj_t *title = lv_label_create(climate_overlay);
            lv_label_set_text(title, entity.name.c_str());
            lv_obj_t *temperature = lv_label_create(climate_overlay);
            if (entity.has_current_temperature && entity.has_target_temperature) {
                lv_label_set_text_fmt(
                    temperature,
                    "Current %.1f C    Target %.1f C",
                    entity.current_temperature,
                    entity.target_temperature
                );
            } else {
                lv_label_set_text(temperature, "Temperature unavailable");
            }
            lv_obj_t *controls = lv_obj_create(climate_overlay);
            lv_obj_set_size(controls, 520, 110);
            lv_obj_set_style_bg_opa(controls, LV_OPA_TRANSP, 0);
            lv_obj_set_style_border_width(controls, 0, 0);
            lv_obj_set_flex_flow(controls, LV_FLEX_FLOW_ROW);
            lv_obj_set_flex_align(
                controls,
                LV_FLEX_ALIGN_SPACE_EVENLY,
                LV_FLEX_ALIGN_CENTER,
                LV_FLEX_ALIGN_CENTER
            );
            const char *symbols[] = {LV_SYMBOL_MINUS, LV_SYMBOL_POWER, LV_SYMBOL_PLUS};
            const char *actions[] = {"temperature_down", "activate", "temperature_up"};
            for (int index = 0; index < 3; ++index) {
                lv_obj_t *button = lv_button_create(controls);
                lv_obj_set_size(button, 110, 80);
                lv_obj_t *label = lv_label_create(button);
                lv_label_set_text(label, symbols[index]);
                lv_obj_center(label);
                lv_obj_add_event_cb(
                    button,
                    [](lv_event_t *control_event) {
                        const char *action = static_cast<const char *>(
                            lv_event_get_user_data(control_event)
                        );
                        if (dashboard_action != nullptr && !selected_climate_id.empty()) {
                            dashboard_action(selected_climate_id.c_str(), action);
                        }
                    },
                    LV_EVENT_CLICKED,
                    const_cast<char *>(actions[index])
                );
            }
            lv_obj_t *close = lv_button_create(climate_overlay);
            lv_obj_set_size(close, 180, 64);
            lv_obj_t *close_label = lv_label_create(close);
            lv_label_set_text(close_label, LV_SYMBOL_CLOSE " Close");
            lv_obj_center(close_label);
            lv_obj_add_event_cb(
                close,
                [](lv_event_t *) {
                    if (climate_overlay != nullptr) {
                        lv_obj_delete(climate_overlay);
                        climate_overlay = nullptr;
                    }
                },
                LV_EVENT_CLICKED,
                nullptr
            );
            return;
        }
    }
    if (dashboard_action != nullptr) {
        dashboard_action(entity_id, "activate");
        ESP_LOGI(kTag, "Dashboard action requested for %s", entity_id);
    }
}

void create_status_screen(
    lv_display_t *display,
    const Tab5BringUpResult &result,
    bool endpoint_provisioned
)
{
    (void)result;
    (void)endpoint_provisioned;
    lv_obj_t *screen = lv_display_get_screen_active(display);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x101820), 0);
    lv_obj_set_style_text_color(screen, lv_color_hex(0xf2f5f7), 0);

    lv_obj_t *panel = lv_obj_create(screen);
    lv_obj_set_size(panel, lv_pct(97), lv_pct(95));
    lv_obj_center(panel);
    lv_obj_set_style_bg_color(panel, lv_color_hex(0x172733), 0);
    lv_obj_set_style_border_color(panel, lv_color_hex(0x2bcbba), 0);
    lv_obj_set_style_border_width(panel, 1, 0);
    lv_obj_set_style_radius(panel, 16, 0);
    lv_obj_set_style_pad_all(panel, 14, 0);
    lv_obj_set_flex_flow(panel, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        panel,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER
    );

    lv_obj_t *header = lv_obj_create(panel);
    lv_obj_set_size(header, lv_pct(100), 64);
    lv_obj_set_style_bg_opa(header, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(header, 0, 0);
    lv_obj_set_style_pad_hor(header, 12, 0);
    lv_obj_set_flex_flow(header, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        header,
        LV_FLEX_ALIGN_SPACE_BETWEEN,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );

    dashboard_area = lv_label_create(header);
    lv_label_set_text(dashboard_area, "Unassigned");
    lv_obj_set_style_text_color(dashboard_area, lv_color_hex(0xf2f5f7), 0);

    lv_obj_t *indicators = lv_obj_create(header);
    lv_obj_set_size(indicators, 220, 48);
    lv_obj_set_style_bg_opa(indicators, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(indicators, 0, 0);
    lv_obj_set_flex_flow(indicators, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(indicators, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

    wireless_status = lv_label_create(indicators);
    lv_label_set_text(wireless_status, LV_SYMBOL_WIFI);
    lv_obj_set_style_text_color(wireless_status, lv_color_hex(0xf6b93b), 0);

    roomhub_status = lv_label_create(indicators);
    lv_label_set_text(roomhub_status, LV_SYMBOL_HOME);
    lv_obj_set_style_text_color(roomhub_status, lv_color_hex(0xf6b93b), 0);

    wake_word_status = lv_label_create(indicators);
    lv_label_set_text(wake_word_status, LV_SYMBOL_AUDIO);
    lv_obj_set_style_text_color(wake_word_status, lv_color_hex(0xf6b93b), 0);

    dashboard_grid = lv_obj_create(panel);
    lv_obj_set_width(dashboard_grid, lv_pct(100));
    lv_obj_set_flex_grow(dashboard_grid, 1);
    lv_obj_set_style_bg_opa(dashboard_grid, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(dashboard_grid, 0, 0);
    lv_obj_set_style_pad_all(dashboard_grid, 8, 0);
    lv_obj_set_style_pad_row(dashboard_grid, 10, 0);
    lv_obj_set_style_pad_column(dashboard_grid, 10, 0);
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
    set_wake_word_status(LV_SYMBOL_AUDIO, 0x2bcbba);
}

void show_tab5_wake_word_detected()
{
    set_wake_word_status(LV_SYMBOL_AUDIO, 0x78e08f);
}

void show_tab5_wireless_scan(unsigned int network_count)
{
    (void)network_count;
    if (wireless_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(wireless_status, LV_SYMBOL_WIFI);
    lv_obj_set_style_text_color(wireless_status, lv_color_hex(0x2bcbba), 0);
    bsp_display_unlock();
}

void show_tab5_wireless_connected()
{
    if (wireless_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(wireless_status, LV_SYMBOL_WIFI);
    lv_obj_set_style_text_color(wireless_status, lv_color_hex(0x2bcbba), 0);
    bsp_display_unlock();
}

void show_tab5_wireless_retrying(unsigned int delay_seconds)
{
    (void)delay_seconds;
    if (wireless_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(wireless_status, LV_SYMBOL_REFRESH);
    lv_obj_set_style_text_color(wireless_status, lv_color_hex(0xf6b93b), 0);
    bsp_display_unlock();
}

void show_tab5_wireless_failed()
{
    if (wireless_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(wireless_status, LV_SYMBOL_WARNING);
    lv_obj_set_style_text_color(wireless_status, lv_color_hex(0xe55039), 0);
    bsp_display_unlock();
}

void show_tab5_roomhub_connecting()
{
    if (roomhub_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(roomhub_status, LV_SYMBOL_REFRESH);
    lv_obj_set_style_text_color(roomhub_status, lv_color_hex(0xf6b93b), 0);
    bsp_display_unlock();
}

void show_tab5_roomhub_retrying(unsigned int delay_seconds)
{
    (void)delay_seconds;
    if (roomhub_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(roomhub_status, LV_SYMBOL_REFRESH);
    lv_obj_set_style_text_color(roomhub_status, lv_color_hex(0xf6b93b), 0);
    bsp_display_unlock();
}

void show_tab5_roomhub_registered()
{
    if (roomhub_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(roomhub_status, LV_SYMBOL_HOME);
    lv_obj_set_style_text_color(roomhub_status, lv_color_hex(0x2bcbba), 0);
    bsp_display_unlock();
}

void show_tab5_firmware_updating(unsigned int percent)
{
    (void)percent;
    if (roomhub_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(roomhub_status, LV_SYMBOL_DOWNLOAD);
    lv_obj_set_style_text_color(roomhub_status, lv_color_hex(0xf6b93b), 0);
    bsp_display_unlock();
}

void show_tab5_firmware_failed()
{
    if (roomhub_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(roomhub_status, LV_SYMBOL_WARNING);
    lv_obj_set_style_text_color(roomhub_status, lv_color_hex(0xe55039), 0);
    bsp_display_unlock();
}

void show_tab5_firmware_restarting()
{
    if (roomhub_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(roomhub_status, LV_SYMBOL_REFRESH);
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
    dashboard_entities = entities;
    dashboard_entity_ids.clear();
    dashboard_entity_ids.reserve(entities.size());
    for (const auto &entity : entities) {
        dashboard_entity_ids.push_back(entity.entity_id);
    }
    lv_label_set_text(dashboard_area, area_name.c_str());
    if (climate_overlay != nullptr) {
        lv_obj_delete(climate_overlay);
        climate_overlay = nullptr;
    }
    lv_obj_clean(dashboard_grid);
    if (entities.empty()) {
        lv_obj_t *empty = lv_label_create(dashboard_grid);
        lv_label_set_text(empty, "No supported entities in this area");
    }
    for (std::size_t index = 0; index < entities.size() && index < 30; ++index) {
        const auto &entity = entities[index];
        lv_obj_t *button = lv_button_create(dashboard_grid);
        lv_obj_set_size(button, 220, 155);
        lv_obj_set_flex_flow(button, LV_FLEX_FLOW_COLUMN);
        lv_obj_set_flex_align(
            button,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER
        );
        lv_obj_set_style_bg_color(
            button,
            lv_color_hex(entity.state == "on" ? 0x2bcbba : 0x34495e),
            0
        );
        if (!entity.available || !entity.actionable) {
            lv_obj_add_state(button, LV_STATE_DISABLED);
        }
        lv_obj_t *icon = lv_label_create(button);
        if (entity.entity_type == "climate") {
            lv_label_set_text_fmt(
                icon,
                entity.has_current_temperature ? "%.1f C" : "-- C",
                entity.current_temperature
            );
        } else if (entity.entity_type == "switch") {
            lv_label_set_text(icon, LV_SYMBOL_POWER);
        } else {
            lv_label_set_text(icon, LV_SYMBOL_BULLET);
        }
        lv_obj_set_style_text_color(
            icon,
            lv_color_hex(entity.state == "on" ? 0xffffff : 0x9fb3c1),
            0
        );
        lv_obj_t *name = lv_label_create(button);
        lv_obj_set_width(name, 190);
        lv_label_set_long_mode(name, LV_LABEL_LONG_DOT);
        lv_obj_set_style_text_align(name, LV_TEXT_ALIGN_CENTER, 0);
        lv_label_set_text(name, entity.name.c_str());
        lv_obj_t *state = lv_label_create(button);
        lv_label_set_text(state, entity.available ? entity.state.c_str() : "Unavailable");
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
