#include "tab5_bringup.hpp"

#include <algorithm>
#include <cstdint>
#include <deque>
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
lv_obj_t *dashboard_tabs = nullptr;
lv_obj_t *dashboard_grid = nullptr;
lv_obj_t *dashboard_pager = nullptr;
lv_obj_t *microphone_privacy_button = nullptr;
lv_obj_t *microphone_privacy_icon = nullptr;
lv_obj_t *microphone_privacy_label = nullptr;
std::vector<std::string> dashboard_entity_ids;
std::vector<DashboardEntity> dashboard_entities;
std::vector<MediaPlayer> room_media_players;
DashboardAction dashboard_action = nullptr;
MicrophoneMuteAction microphone_mute_action = nullptr;
bool microphone_is_muted = false;
lv_obj_t *control_overlay = nullptr;
std::string selected_control_id;
std::string selected_dashboard_group = "home";
std::size_t selected_dashboard_page = 0;
lv_obj_t *media_overlay = nullptr;
lv_obj_t *notification_overlay = nullptr;
lv_timer_t *notification_timer = nullptr;
std::string notification_delivery_id;
NotificationAction notification_action = nullptr;
NotificationButtonAction notification_button_action = nullptr;
NotificationButtons notification_buttons;
struct PendingNotification {
    std::string delivery_id;
    std::string title;
    std::string text;
    bool emergency;
    unsigned int timeout_seconds;
    NotificationButtons buttons;
    NotificationAction action;
    NotificationButtonAction button_action;
};
std::deque<PendingNotification> pending_notifications;
std::size_t selected_media_player = 0;
constexpr std::size_t kDashboardPageSize = 15;
constexpr uint32_t kPrimaryTextColor = 0xf7fafc;
constexpr uint32_t kSecondaryTextColor = 0xcbd5df;

void style_high_contrast_text(lv_obj_t *label)
{
    lv_obj_set_style_text_color(label, lv_color_hex(kPrimaryTextColor), 0);
}

bool entity_matches_group(const DashboardEntity &entity, const std::string &group)
{
    return group == "all"
        || (group == "favourites" && entity.pinned)
        || (group == "climate"
            && (entity.entity_type == "climate" || entity.entity_type == "fan"))
        || (group == "actions"
            && (entity.entity_type == "scene" || entity.entity_type == "script"))
        || group == entity.entity_type;
}

std::vector<std::size_t> dashboard_indices_for_group(const std::string &group)
{
    std::vector<std::size_t> indices;
    for (std::size_t index = 0; index < dashboard_entities.size(); ++index) {
        if (entity_matches_group(dashboard_entities[index], group)) {
            indices.push_back(index);
        }
    }
    return indices;
}

uint32_t dashboard_tile_color(const DashboardEntity &entity)
{
    if (!entity.available) {
        return 0x3b4652;
    }
    if (entity.entity_type == "light") {
        return entity.state == "on" ? 0xc78b2d : 0x34495e;
    }
    if (entity.entity_type == "switch") {
        return entity.state == "on" ? 0x238f83 : 0x34495e;
    }
    if (entity.entity_type == "climate") {
        if (entity.hvac_action == "heating") {
            return 0xc85f35;
        }
        if (entity.hvac_action == "cooling") {
            return 0x2878a8;
        }
        return entity.state == "off" ? 0x34495e : 0x416b7b;
    }
    if (entity.entity_type == "fan") {
        return entity.state == "on" ? 0x2878a8 : 0x34495e;
    }
    if (entity.entity_type == "cover") {
        return entity.state == "open" ? 0x596fa3 : 0x34495e;
    }
    if (entity.entity_type == "scene" || entity.entity_type == "script") {
        return 0x75579b;
    }
    return 0x34495e;
}

void render_dashboard_content();
void show_media_overlay();
void render_notification(const PendingNotification &notification);

void update_microphone_privacy_tile()
{
    if (microphone_privacy_button == nullptr
        || microphone_privacy_icon == nullptr
        || microphone_privacy_label == nullptr) {
        return;
    }
    lv_obj_set_style_bg_color(
        microphone_privacy_button,
        lv_color_hex(microphone_is_muted ? 0xa33b32 : 0x238f83),
        0
    );
    lv_label_set_text(
        microphone_privacy_icon,
        microphone_is_muted ? LV_SYMBOL_MUTE : "MIC"
    );
    lv_label_set_text(
        microphone_privacy_label,
        microphone_is_muted ? "Microphone\nMuted" : "Microphone\nListening"
    );
}

void finish_notification(const char *status)
{
    const std::string delivery_id = notification_delivery_id;
    NotificationAction action = notification_action;
    if (notification_timer != nullptr) {
        lv_timer_delete(notification_timer);
        notification_timer = nullptr;
    }
    if (notification_overlay != nullptr) {
        lv_obj_delete(notification_overlay);
        notification_overlay = nullptr;
    }
    notification_delivery_id.clear();
    notification_action = nullptr;
    notification_button_action = nullptr;
    notification_buttons.count = 0;
    if (action != nullptr && !delivery_id.empty()) {
        action(delivery_id.c_str(), status);
    }
    if (!pending_notifications.empty()) {
        PendingNotification next = std::move(pending_notifications.front());
        pending_notifications.pop_front();
        render_notification(next);
    }
}

void close_notification_overlay(lv_event_t *)
{
    finish_notification("dismissed");
}

void expire_notification(lv_timer_t *)
{
    notification_timer = nullptr;
    finish_notification("expired");
}

void activate_notification_button(lv_event_t *event)
{
    const char *entity_id = static_cast<const char *>(
        lv_event_get_user_data(event)
    );
    if (notification_button_action != nullptr && entity_id != nullptr
        && !notification_delivery_id.empty()) {
        notification_button_action(notification_delivery_id.c_str(), entity_id);
        finish_notification("dismissed");
    }
}

void on_dashboard_group(lv_event_t *event)
{
    const char *group = static_cast<const char *>(lv_event_get_user_data(event));
    if (group == nullptr) {
        return;
    }
    if (std::string(group) == "media") {
        show_media_overlay();
        return;
    }
    selected_dashboard_group = group;
    selected_dashboard_page = 0;
    render_dashboard_content();
}

void on_dashboard_page(lv_event_t *event)
{
    const intptr_t direction = reinterpret_cast<intptr_t>(
        lv_event_get_user_data(event)
    );
    const auto indices = dashboard_indices_for_group(selected_dashboard_group);
    const std::size_t page_count = (indices.size() + kDashboardPageSize - 1)
        / kDashboardPageSize;
    if (direction < 0 && selected_dashboard_page > 0) {
        --selected_dashboard_page;
    } else if (direction > 0 && selected_dashboard_page + 1 < page_count) {
        ++selected_dashboard_page;
    }
    render_dashboard_content();
}

void set_wake_word_status(const char *text, uint32_t color)
{
    if (wake_word_status == nullptr || !bsp_display_lock(0)) {
        return;
    }
    lv_label_set_text(wake_word_status, text);
    lv_obj_set_style_text_color(wake_word_status, lv_color_hex(color), 0);
    bsp_display_unlock();
}

void on_microphone_icon(lv_event_t *)
{
    if (microphone_mute_action != nullptr) microphone_mute_action();
}

void on_microphone_tile(lv_event_t *)
{
    on_microphone_icon(nullptr);
}

void send_selected_control(lv_event_t *event)
{
    const char *action = static_cast<const char *>(lv_event_get_user_data(event));
    if (dashboard_action != nullptr && action != nullptr
        && !selected_control_id.empty()) {
        dashboard_action(selected_control_id.c_str(), action, -1);
    }
}

void add_control_button(lv_obj_t *parent, const char *label_text, const char *action)
{
    lv_obj_t *button = lv_button_create(parent);
    lv_obj_set_size(button, 118, 80);
    lv_obj_t *label = lv_label_create(button);
    lv_label_set_text(label, label_text);
    style_high_contrast_text(label);
    lv_obj_center(label);
    lv_obj_add_event_cb(
        button,
        send_selected_control,
        LV_EVENT_CLICKED,
        const_cast<char *>(action)
    );
}

void close_control_overlay(lv_event_t *)
{
    if (control_overlay != nullptr) {
        lv_obj_delete(control_overlay);
        control_overlay = nullptr;
    }
}

void send_brightness_slider(lv_event_t *event)
{
    lv_obj_t *slider = static_cast<lv_obj_t *>(lv_event_get_target(event));
    if (dashboard_action != nullptr && !selected_control_id.empty()) {
        dashboard_action(
            selected_control_id.c_str(),
            "brightness_set",
            lv_slider_get_value(slider)
        );
    }
}

void show_control_overlay(const DashboardEntity &entity)
{
    selected_control_id = entity.entity_id;
    control_overlay = lv_obj_create(lv_screen_active());
    lv_obj_set_size(control_overlay, 650, 430);
    lv_obj_center(control_overlay);
    lv_obj_set_style_bg_color(control_overlay, lv_color_hex(0x172733), 0);
    lv_obj_set_style_border_color(control_overlay, lv_color_hex(0x2bcbba), 0);
    lv_obj_set_style_border_width(control_overlay, 2, 0);
    lv_obj_set_style_radius(control_overlay, 22, 0);
    lv_obj_set_flex_flow(control_overlay, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        control_overlay,
        LV_FLEX_ALIGN_SPACE_EVENLY,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );

    lv_obj_t *title = lv_label_create(control_overlay);
    lv_label_set_text(title, entity.name.c_str());
    style_high_contrast_text(title);
    lv_obj_t *detail = lv_label_create(control_overlay);
    style_high_contrast_text(detail);
    if (entity.entity_type == "climate" && entity.has_current_temperature
        && entity.has_target_temperature) {
        lv_label_set_text_fmt(
            detail,
            "Current %.1f C    Target %.1f C",
            entity.current_temperature,
            entity.target_temperature
        );
    } else if (entity.entity_type == "light" && entity.has_brightness) {
        lv_label_set_text_fmt(detail, "Brightness %d%%", entity.brightness * 100 / 255);
    } else if (entity.entity_type == "fan" && entity.has_percentage) {
        lv_label_set_text_fmt(detail, "Speed %d%%", entity.percentage);
    } else if (entity.entity_type == "cover" && entity.has_current_position) {
        lv_label_set_text_fmt(detail, "Position %d%%", entity.current_position);
    } else if (entity.entity_type == "script") {
        lv_label_set_text(detail, "Run this action?");
    } else {
        lv_label_set_text(detail, entity.state.c_str());
    }
    if (entity.entity_type == "climate") {
        lv_obj_t *mode = lv_label_create(control_overlay);
        const std::string mode_text = "Mode: " + entity.state;
        lv_label_set_text(mode, mode_text.c_str());
        style_high_contrast_text(mode);
    }

    lv_obj_t *controls = lv_obj_create(control_overlay);
    lv_obj_set_size(controls, 590, 110);
    lv_obj_set_style_bg_opa(controls, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(controls, 0, 0);
    lv_obj_set_flex_flow(controls, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        controls,
        LV_FLEX_ALIGN_SPACE_EVENLY,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    if (entity.entity_type == "light") {
        lv_obj_t *slider = lv_slider_create(controls);
        lv_obj_set_size(slider, 360, 28);
        lv_slider_set_range(slider, 1, 255);
        lv_slider_set_value(
            slider,
            entity.has_brightness ? entity.brightness : 128,
            LV_ANIM_OFF
        );
        lv_obj_add_event_cb(
            slider,
            send_brightness_slider,
            LV_EVENT_RELEASED,
            nullptr
        );
        add_control_button(controls, LV_SYMBOL_POWER, "activate");
    } else if (entity.entity_type == "climate") {
        add_control_button(controls, LV_SYMBOL_MINUS, "temperature_down");
        add_control_button(controls, LV_SYMBOL_POWER, "activate");
        add_control_button(controls, "Mode", "mode_next");
        add_control_button(controls, LV_SYMBOL_PLUS, "temperature_up");
    } else if (entity.entity_type == "fan") {
        add_control_button(controls, LV_SYMBOL_MINUS, "percentage_down");
        add_control_button(controls, LV_SYMBOL_POWER, "activate");
        add_control_button(controls, LV_SYMBOL_PLUS, "percentage_up");
    } else if (entity.entity_type == "cover") {
        add_control_button(controls, LV_SYMBOL_UP " Open", "cover_open");
        add_control_button(controls, LV_SYMBOL_STOP " Stop", "cover_stop");
        add_control_button(controls, LV_SYMBOL_DOWN " Close", "cover_close");
    } else {
        add_control_button(controls, LV_SYMBOL_PLAY " Run", "activate");
    }

    lv_obj_t *close = lv_button_create(control_overlay);
    lv_obj_set_size(close, 180, 64);
    lv_obj_t *close_label = lv_label_create(close);
    lv_label_set_text(close_label, LV_SYMBOL_CLOSE " Close");
    style_high_contrast_text(close_label);
    lv_obj_center(close_label);
    lv_obj_add_event_cb(close, close_control_overlay, LV_EVENT_CLICKED, nullptr);
}

void on_dashboard_touch(lv_event_t *event)
{
    const char *entity_id = static_cast<const char *>(lv_event_get_user_data(event));
    if (dashboard_action == nullptr || entity_id == nullptr) {
        return;
    }
    for (const auto &entity : dashboard_entities) {
        if (entity.entity_id != entity_id) {
            continue;
        }
        if (entity.entity_type == "switch" || entity.entity_type == "scene") {
            dashboard_action(entity_id, "activate", -1);
        } else {
            show_control_overlay(entity);
        }
        ESP_LOGI(kTag, "Dashboard control requested for %s", entity_id);
        return;
    }
}

void close_media_overlay(lv_event_t *)
{
    if (media_overlay != nullptr) {
        lv_obj_delete(media_overlay);
        media_overlay = nullptr;
    }
}

void send_media_action(lv_event_t *event)
{
    const char *action = static_cast<const char *>(lv_event_get_user_data(event));
    if (dashboard_action == nullptr || action == nullptr
        || selected_media_player >= room_media_players.size()) {
        return;
    }
    dashboard_action(
        room_media_players[selected_media_player].entity_id.c_str(),
        action,
        -1
    );
}

void add_media_button(lv_obj_t *parent, const char *label_text, const char *action)
{
    lv_obj_t *button = lv_button_create(parent);
    lv_obj_set_size(button, 118, 72);
    lv_obj_t *label = lv_label_create(button);
    lv_label_set_text(label, label_text);
    style_high_contrast_text(label);
    lv_obj_center(label);
    lv_obj_add_event_cb(
        button,
        send_media_action,
        LV_EVENT_CLICKED,
        const_cast<char *>(action)
    );
}

void send_media_volume(lv_event_t *event)
{
    if (dashboard_action == nullptr
        || selected_media_player >= room_media_players.size()) {
        return;
    }
    lv_obj_t *slider = static_cast<lv_obj_t *>(lv_event_get_target(event));
    dashboard_action(
        room_media_players[selected_media_player].entity_id.c_str(),
        "media_volume_set",
        lv_slider_get_value(slider)
    );
}

void select_media_player(lv_event_t *event)
{
    selected_media_player = reinterpret_cast<std::size_t>(
        lv_event_get_user_data(event)
    );
    if (media_overlay != nullptr) {
        lv_obj_delete(media_overlay);
        media_overlay = nullptr;
    }
    show_media_overlay();
}

void show_media_overlay()
{
    if (media_overlay != nullptr) {
        return;
    }
    media_overlay = lv_obj_create(lv_screen_active());
    lv_obj_set_size(media_overlay, 700, 500);
    lv_obj_center(media_overlay);
    lv_obj_set_style_bg_color(media_overlay, lv_color_hex(0x172733), 0);
    lv_obj_set_style_border_color(media_overlay, lv_color_hex(0x75579b), 0);
    lv_obj_set_style_border_width(media_overlay, 2, 0);
    lv_obj_set_style_radius(media_overlay, 22, 0);
    lv_obj_set_flex_flow(media_overlay, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        media_overlay,
        LV_FLEX_ALIGN_SPACE_EVENLY,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    lv_obj_t *heading = lv_label_create(media_overlay);
    lv_label_set_text(heading, LV_SYMBOL_AUDIO " Room media");
    style_high_contrast_text(heading);
    if (room_media_players.empty()) {
        lv_obj_t *empty = lv_label_create(media_overlay);
        lv_label_set_text(empty, "No visible media players in this area");
        style_high_contrast_text(empty);
    } else {
        if (selected_media_player >= room_media_players.size()) {
            selected_media_player = 0;
        }
        lv_obj_t *players = lv_obj_create(media_overlay);
        lv_obj_set_size(players, 640, 54);
        lv_obj_set_style_bg_opa(players, LV_OPA_TRANSP, 0);
        lv_obj_set_style_border_width(players, 0, 0);
        lv_obj_set_flex_flow(players, LV_FLEX_FLOW_ROW);
        lv_obj_set_flex_align(
            players,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER
        );
        for (std::size_t index = 0; index < room_media_players.size(); ++index) {
            lv_obj_t *button = lv_button_create(players);
            lv_obj_set_height(button, 42);
            lv_obj_set_style_bg_color(
                button,
                lv_color_hex(index == selected_media_player ? 0x75579b : 0x34495e),
                0
            );
            lv_obj_t *label = lv_label_create(button);
            lv_label_set_text(label, room_media_players[index].name.c_str());
            style_high_contrast_text(label);
            lv_obj_center(label);
            lv_obj_add_event_cb(
                button,
                select_media_player,
                LV_EVENT_CLICKED,
                reinterpret_cast<void *>(index)
            );
        }
        const auto &player = room_media_players[selected_media_player];
        lv_obj_t *track = lv_label_create(media_overlay);
        lv_obj_set_width(track, 620);
        lv_label_set_long_mode(track, LV_LABEL_LONG_DOT);
        lv_obj_set_style_text_align(track, LV_TEXT_ALIGN_CENTER, 0);
        const std::string title = player.media_title.empty()
            ? player.state : player.media_title;
        lv_label_set_text(track, title.c_str());
        style_high_contrast_text(track);
        lv_obj_t *artist = lv_label_create(media_overlay);
        lv_label_set_text(
            artist,
            player.media_artist.empty() ? player.source.c_str() : player.media_artist.c_str()
        );
        lv_obj_set_style_text_color(artist, lv_color_hex(kSecondaryTextColor), 0);
        lv_obj_t *transport = lv_obj_create(media_overlay);
        lv_obj_set_size(transport, 520, 90);
        lv_obj_set_style_bg_opa(transport, LV_OPA_TRANSP, 0);
        lv_obj_set_style_border_width(transport, 0, 0);
        lv_obj_set_flex_flow(transport, LV_FLEX_FLOW_ROW);
        lv_obj_set_flex_align(
            transport,
            LV_FLEX_ALIGN_SPACE_EVENLY,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER
        );
        add_media_button(transport, LV_SYMBOL_PREV, "media_previous");
        add_media_button(
            transport,
            player.state == "playing" ? LV_SYMBOL_PAUSE : LV_SYMBOL_PLAY,
            "media_play_pause"
        );
        add_media_button(transport, LV_SYMBOL_NEXT, "media_next");
        lv_obj_t *volume_row = lv_obj_create(media_overlay);
        lv_obj_set_size(volume_row, 600, 55);
        lv_obj_set_style_bg_opa(volume_row, LV_OPA_TRANSP, 0);
        lv_obj_set_style_border_width(volume_row, 0, 0);
        lv_obj_set_flex_flow(volume_row, LV_FLEX_FLOW_ROW);
        lv_obj_set_flex_align(
            volume_row,
            LV_FLEX_ALIGN_SPACE_EVENLY,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER
        );
        lv_obj_t *volume_icon = lv_label_create(volume_row);
        lv_label_set_text(volume_icon, LV_SYMBOL_VOLUME_MAX);
        style_high_contrast_text(volume_icon);
        lv_obj_t *volume = lv_slider_create(volume_row);
        lv_obj_set_size(volume, 410, 24);
        lv_slider_set_range(volume, 0, 100);
        lv_slider_set_value(volume, player.volume_percent, LV_ANIM_OFF);
        lv_obj_add_event_cb(volume, send_media_volume, LV_EVENT_RELEASED, nullptr);
        lv_obj_t *source = lv_button_create(media_overlay);
        lv_obj_set_size(source, 260, 48);
        lv_obj_t *source_label = lv_label_create(source);
        const std::string source_text = player.source.empty()
            ? "Next source" : "Source: " + player.source;
        lv_label_set_text(source_label, source_text.c_str());
        style_high_contrast_text(source_label);
        lv_obj_center(source_label);
        lv_obj_add_event_cb(
            source,
            send_media_action,
            LV_EVENT_CLICKED,
            const_cast<char *>("media_source_next")
        );
    }
    lv_obj_t *close = lv_button_create(media_overlay);
    lv_obj_set_size(close, 160, 50);
    lv_obj_t *close_label = lv_label_create(close);
    lv_label_set_text(close_label, LV_SYMBOL_CLOSE " Close");
    style_high_contrast_text(close_label);
    lv_obj_center(close_label);
    lv_obj_add_event_cb(close, close_media_overlay, LV_EVENT_CLICKED, nullptr);
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

    dashboard_tabs = lv_obj_create(panel);
    lv_obj_set_size(dashboard_tabs, lv_pct(100), 44);
    lv_obj_set_style_bg_opa(dashboard_tabs, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(dashboard_tabs, 0, 0);
    lv_obj_set_style_pad_all(dashboard_tabs, 2, 0);
    lv_obj_set_flex_flow(dashboard_tabs, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        dashboard_tabs,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );

    dashboard_grid = lv_obj_create(panel);
    lv_obj_set_width(dashboard_grid, lv_pct(100));
    lv_obj_set_flex_grow(dashboard_grid, 1);
    lv_obj_set_style_bg_opa(dashboard_grid, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(dashboard_grid, 0, 0);
    lv_obj_set_style_pad_all(dashboard_grid, 5, 0);
    lv_obj_set_style_pad_row(dashboard_grid, 8, 0);
    lv_obj_set_style_pad_column(dashboard_grid, 10, 0);
    lv_obj_set_flex_flow(dashboard_grid, LV_FLEX_FLOW_ROW_WRAP);
    lv_obj_set_flex_align(
        dashboard_grid,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_START
    );

    dashboard_pager = lv_obj_create(panel);
    lv_obj_set_size(dashboard_pager, lv_pct(100), 42);
    lv_obj_set_style_bg_opa(dashboard_pager, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(dashboard_pager, 0, 0);
    lv_obj_set_style_pad_all(dashboard_pager, 2, 0);
    lv_obj_set_flex_flow(dashboard_pager, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        dashboard_pager,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
}

void render_dashboard_content()
{
    if (dashboard_tabs == nullptr || dashboard_grid == nullptr
        || dashboard_pager == nullptr) {
        return;
    }

    microphone_privacy_button = nullptr;
    microphone_privacy_icon = nullptr;
    microphone_privacy_label = nullptr;
    lv_obj_clean(dashboard_tabs);
    lv_obj_clean(dashboard_grid);
    lv_obj_clean(dashboard_pager);

    if (selected_dashboard_group == "home") {
        selected_dashboard_page = 0;
        lv_obj_add_flag(dashboard_tabs, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(dashboard_pager, LV_OBJ_FLAG_HIDDEN);
        const char *group_ids[] = {
            "favourites", "light", "switch", "climate", "cover", "actions", "media"
        };
        const char *group_labels[] = {
            "Favourites", "Lights", "Switches", "Climate", "Covers", "Actions", "Media"
        };
        const char *group_icons[] = {
            "*", LV_SYMBOL_CHARGE, LV_SYMBOL_POWER, LV_SYMBOL_TINT,
            LV_SYMBOL_BARS, LV_SYMBOL_PLAY, LV_SYMBOL_AUDIO
        };
        const uint32_t group_colors[] = {
            0x8a6b27, 0xa87324, 0x238f83, 0x416b7b,
            0x596fa3, 0x75579b, 0x7b4f78
        };
        for (std::size_t group_index = 0; group_index < 7; ++group_index) {
            const auto matching = dashboard_indices_for_group(group_ids[group_index]);
            const std::size_t matching_count = std::string(group_ids[group_index]) == "media"
                ? room_media_players.size() : matching.size();
            if (matching_count == 0) {
                continue;
            }
            lv_obj_t *group_button = lv_button_create(dashboard_grid);
            lv_obj_set_size(group_button, 280, 220);
            lv_obj_set_flex_flow(group_button, LV_FLEX_FLOW_COLUMN);
            lv_obj_set_flex_align(
                group_button,
                LV_FLEX_ALIGN_CENTER,
                LV_FLEX_ALIGN_CENTER,
                LV_FLEX_ALIGN_CENTER
            );
            lv_obj_set_style_bg_color(
                group_button,
                lv_color_hex(group_colors[group_index]),
                0
            );
            lv_obj_set_style_radius(group_button, 22, 0);
            lv_obj_t *icon = lv_label_create(group_button);
            lv_label_set_text(icon, group_icons[group_index]);
            lv_obj_set_style_text_font(icon, &lv_font_montserrat_36, 0);
            lv_obj_t *label = lv_label_create(group_button);
            lv_label_set_text_fmt(
                label,
                "%s  (%u)",
                group_labels[group_index],
                static_cast<unsigned int>(matching_count)
            );
            style_high_contrast_text(label);
            lv_obj_set_style_text_font(label, &lv_font_montserrat_28, 0);
            lv_obj_add_event_cb(
                group_button,
                on_dashboard_group,
                LV_EVENT_CLICKED,
                const_cast<char *>(group_ids[group_index])
            );
        }
        microphone_privacy_button = lv_button_create(dashboard_grid);
        lv_obj_set_size(microphone_privacy_button, 280, 220);
        lv_obj_set_flex_flow(microphone_privacy_button, LV_FLEX_FLOW_COLUMN);
        lv_obj_set_flex_align(
            microphone_privacy_button,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER
        );
        lv_obj_set_style_radius(microphone_privacy_button, 22, 0);
        microphone_privacy_icon = lv_label_create(microphone_privacy_button);
        lv_obj_set_style_text_font(microphone_privacy_icon, &lv_font_montserrat_36, 0);
        microphone_privacy_label = lv_label_create(microphone_privacy_button);
        lv_obj_set_style_text_align(microphone_privacy_label, LV_TEXT_ALIGN_CENTER, 0);
        style_high_contrast_text(microphone_privacy_label);
        lv_obj_set_style_text_font(microphone_privacy_label, &lv_font_montserrat_28, 0);
        update_microphone_privacy_tile();
        lv_obj_add_event_cb(
            microphone_privacy_button, on_microphone_tile, LV_EVENT_CLICKED, nullptr
        );
        if (dashboard_entities.empty()) {
            lv_obj_t *empty = lv_label_create(dashboard_grid);
            lv_label_set_text(empty, "No supported entities in this area");
            style_high_contrast_text(empty);
        }
        return;
    }

    const auto selected_indices = dashboard_indices_for_group(
        selected_dashboard_group
    );
    if (selected_indices.empty()) {
        selected_dashboard_group = "home";
        selected_dashboard_page = 0;
        render_dashboard_content();
        return;
    }

    lv_obj_remove_flag(dashboard_tabs, LV_OBJ_FLAG_HIDDEN);
    lv_obj_t *home = lv_button_create(dashboard_tabs);
    lv_obj_set_height(home, 36);
    lv_obj_set_style_pad_hor(home, 16, 0);
    lv_obj_set_style_bg_color(home, lv_color_hex(0x238f83), 0);
    lv_obj_t *home_label = lv_label_create(home);
    lv_label_set_text(home_label, LV_SYMBOL_HOME " Groups");
    style_high_contrast_text(home_label);
    lv_obj_center(home_label);
    lv_obj_add_event_cb(
        home,
        on_dashboard_group,
        LV_EVENT_CLICKED,
        const_cast<char *>("home")
    );
    const char *selected_label = selected_dashboard_group == "favourites"
        ? "Favourites"
        : (selected_dashboard_group == "light" ? "Lights"
            : (selected_dashboard_group == "switch" ? "Switches"
                : (selected_dashboard_group == "climate" ? "Climate"
                    : (selected_dashboard_group == "cover" ? "Covers" : "Actions"))));
    lv_obj_t *group_title = lv_label_create(dashboard_tabs);
    lv_obj_set_width(group_title, 220);
    lv_obj_set_style_text_align(group_title, LV_TEXT_ALIGN_CENTER, 0);
    style_high_contrast_text(group_title);
    lv_label_set_text(group_title, selected_label);

    const auto indices = dashboard_indices_for_group(selected_dashboard_group);
    const std::size_t page_count = indices.empty() ? 1
        : (indices.size() + kDashboardPageSize - 1) / kDashboardPageSize;
    if (selected_dashboard_page >= page_count) {
        selected_dashboard_page = page_count - 1;
    }
    const std::size_t first = selected_dashboard_page * kDashboardPageSize;
    const std::size_t last = std::min(first + kDashboardPageSize, indices.size());

    if (indices.empty()) {
        lv_obj_t *empty = lv_label_create(dashboard_grid);
        lv_label_set_text(empty, "No entities in this group");
        style_high_contrast_text(empty);
    }
    for (std::size_t visible_index = first; visible_index < last; ++visible_index) {
        const std::size_t index = indices[visible_index];
        const auto &entity = dashboard_entities[index];
        lv_obj_t *button = lv_button_create(dashboard_grid);
        lv_obj_set_size(button, 220, 142);
        lv_obj_set_flex_flow(button, LV_FLEX_FLOW_COLUMN);
        lv_obj_set_flex_align(
            button,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER,
            LV_FLEX_ALIGN_CENTER
        );
        lv_obj_set_style_bg_color(
            button,
            lv_color_hex(dashboard_tile_color(entity)),
            0
        );
        lv_obj_set_style_radius(button, 16, 0);
        if (entity.pinned) {
            lv_obj_set_style_border_width(button, 3, 0);
            lv_obj_set_style_border_color(button, lv_color_hex(0xffd166), 0);
        }
        if (!entity.available || !entity.actionable) {
            lv_obj_set_style_opa(button, LV_OPA_60, 0);
            lv_obj_add_state(button, LV_STATE_DISABLED);
        }

        lv_obj_t *icon = lv_label_create(button);
        if (entity.entity_type == "climate") {
            lv_label_set_text_fmt(
                icon,
                entity.has_current_temperature
                    ? LV_SYMBOL_TINT " %.1f C" : LV_SYMBOL_TINT " -- C",
                entity.current_temperature
            );
        } else if (entity.entity_type == "switch") {
            lv_label_set_text(icon, LV_SYMBOL_POWER);
        } else if (entity.entity_type == "fan") {
            lv_label_set_text(icon, LV_SYMBOL_REFRESH);
        } else if (entity.entity_type == "cover") {
            lv_label_set_text(icon, LV_SYMBOL_BARS);
        } else if (entity.entity_type == "scene" || entity.entity_type == "script") {
            lv_label_set_text(icon, LV_SYMBOL_PLAY);
        } else {
            lv_label_set_text(icon, LV_SYMBOL_CHARGE);
        }
        lv_obj_set_style_text_color(
            icon,
            lv_color_hex(entity.available ? 0xffffff : 0xb0bac4),
            0
        );
        lv_obj_set_style_text_font(icon, &lv_font_montserrat_36, 0);

        lv_obj_t *name = lv_label_create(button);
        lv_obj_set_width(name, 190);
        lv_label_set_long_mode(name, LV_LABEL_LONG_DOT);
        lv_obj_set_style_text_align(name, LV_TEXT_ALIGN_CENTER, 0);
        lv_obj_set_style_text_color(name, lv_color_hex(kPrimaryTextColor), 0);
        lv_obj_set_style_text_font(name, &lv_font_montserrat_28, 0);
        lv_label_set_text(name, entity.name.c_str());
        if (entity.actionable) {
            lv_obj_add_event_cb(
                button,
                on_dashboard_touch,
                LV_EVENT_CLICKED,
                const_cast<char *>(dashboard_entity_ids[index].c_str())
            );
        }
    }

    if (page_count > 1) {
        lv_obj_remove_flag(dashboard_pager, LV_OBJ_FLAG_HIDDEN);
        lv_obj_t *previous = lv_button_create(dashboard_pager);
        lv_obj_set_size(previous, 54, 34);
        if (selected_dashboard_page == 0) {
            lv_obj_add_state(previous, LV_STATE_DISABLED);
        }
        lv_obj_t *previous_label = lv_label_create(previous);
        lv_label_set_text(previous_label, LV_SYMBOL_LEFT);
        style_high_contrast_text(previous_label);
        lv_obj_center(previous_label);
        lv_obj_add_event_cb(
            previous,
            on_dashboard_page,
            LV_EVENT_CLICKED,
            reinterpret_cast<void *>(-1)
        );

        lv_obj_t *page_label = lv_label_create(dashboard_pager);
        lv_obj_set_width(page_label, 100);
        lv_obj_set_style_text_align(page_label, LV_TEXT_ALIGN_CENTER, 0);
        style_high_contrast_text(page_label);
        lv_label_set_text_fmt(
            page_label,
            "%u / %u",
            static_cast<unsigned int>(selected_dashboard_page + 1),
            static_cast<unsigned int>(page_count)
        );

        lv_obj_t *next = lv_button_create(dashboard_pager);
        lv_obj_set_size(next, 54, 34);
        if (selected_dashboard_page + 1 >= page_count) {
            lv_obj_add_state(next, LV_STATE_DISABLED);
        }
        lv_obj_t *next_label = lv_label_create(next);
        lv_label_set_text(next_label, LV_SYMBOL_RIGHT);
        style_high_contrast_text(next_label);
        lv_obj_center(next_label);
        lv_obj_add_event_cb(
            next,
            on_dashboard_page,
            LV_EVENT_CLICKED,
            reinterpret_cast<void *>(1)
        );
    } else {
        lv_obj_add_flag(dashboard_pager, LV_OBJ_FLAG_HIDDEN);
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
    microphone_is_muted = false;
    set_wake_word_status(LV_SYMBOL_AUDIO, 0x2bcbba);
    if (dashboard_grid != nullptr && selected_dashboard_group == "home"
        && bsp_display_lock(0)) {
        update_microphone_privacy_tile();
        bsp_display_unlock();
    }
}

void show_tab5_wake_word_detected()
{
    set_wake_word_status(LV_SYMBOL_AUDIO, 0x78e08f);
}

void show_tab5_microphone_muted()
{
    microphone_is_muted = true;
    set_wake_word_status(LV_SYMBOL_MUTE, 0xe55039);
    if (dashboard_grid != nullptr && selected_dashboard_group == "home"
        && bsp_display_lock(0)) {
        update_microphone_privacy_tile();
        bsp_display_unlock();
    }
}

void set_tab5_microphone_mute_action(MicrophoneMuteAction action)
{
    microphone_mute_action = action;
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

bool set_tab5_screen_on(bool screen_on)
{
    const esp_err_t result = bsp_display_brightness_set(screen_on ? 35 : 0);
    if (result != ESP_OK) {
        ESP_LOGW(kTag, "Could not set display power: %s", esp_err_to_name(result));
    }
    return result == ESP_OK;
}

void show_tab5_dashboard(
    const std::string &area_name,
    const std::vector<DashboardEntity> &entities,
    const std::vector<MediaPlayer> &media_players,
    DashboardAction action
)
{
    if (dashboard_area == nullptr || dashboard_grid == nullptr || !bsp_display_lock(0)) {
        return;
    }
    dashboard_action = action;
    dashboard_entities = entities;
    room_media_players = media_players;
    dashboard_entity_ids.clear();
    dashboard_entity_ids.reserve(entities.size());
    for (const auto &entity : entities) {
        dashboard_entity_ids.push_back(entity.entity_id);
    }
    lv_label_set_text(dashboard_area, area_name.c_str());
    render_dashboard_content();
    bsp_display_unlock();
}

void show_tab5_notification(
    const std::string &delivery_id,
    const std::string &title_text,
    const std::string &body_text,
    bool emergency,
    unsigned int timeout_seconds,
    bool queue,
    const NotificationButtons &buttons,
    NotificationAction action,
    NotificationButtonAction button_action
)
{
    if (!bsp_display_lock(0)) {
        return;
    }
    if (notification_overlay != nullptr) {
        if (queue) {
            if (pending_notifications.size() < 8) {
                pending_notifications.push_back({
                    delivery_id, title_text, body_text, emergency,
                    timeout_seconds, buttons, action, button_action
                });
            } else if (action != nullptr) {
                action(delivery_id.c_str(), "replaced");
            }
            bsp_display_unlock();
            return;
        }
        pending_notifications.clear();
        finish_notification("replaced");
    }
    render_notification({
        delivery_id, title_text, body_text, emergency, timeout_seconds,
        buttons, action, button_action
    });
    bsp_display_unlock();
}

namespace {

void render_notification(const PendingNotification &notification)
{
    notification_delivery_id = notification.delivery_id;
    notification_action = notification.action;
    notification_button_action = notification.button_action;
    notification_buttons = notification.buttons;
    notification_overlay = lv_obj_create(lv_screen_active());
    lv_obj_set_size(notification_overlay, 700, 430);
    lv_obj_center(notification_overlay);
    lv_obj_set_style_bg_color(notification_overlay, lv_color_hex(0x172733), 0);
    lv_obj_set_style_border_color(
        notification_overlay,
        lv_color_hex(notification.emergency ? 0xe5534b : 0x2bcbba),
        0
    );
    lv_obj_set_style_border_width(notification_overlay, 4, 0);
    lv_obj_set_style_radius(notification_overlay, 22, 0);
    lv_obj_set_style_pad_all(notification_overlay, 28, 0);
    lv_obj_set_flex_flow(notification_overlay, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(
        notification_overlay,
        LV_FLEX_ALIGN_START,
        LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );

    lv_obj_t *title = lv_label_create(notification_overlay);
    lv_label_set_text(title, notification.title.c_str());
    lv_obj_set_style_text_color(
        title,
        lv_color_hex(notification.emergency ? 0xff7b72 : 0x55e6d5),
        0
    );
    lv_obj_set_style_text_font(title, &lv_font_montserrat_28, 0);

    lv_obj_t *body = lv_label_create(notification_overlay);
    lv_obj_set_width(body, lv_pct(92));
    lv_label_set_long_mode(body, LV_LABEL_LONG_WRAP);
    lv_label_set_text(body, notification.text.c_str());
    lv_obj_set_style_text_align(body, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(body, lv_color_hex(0xf2f5f7), 0);
    lv_obj_set_style_text_font(body, LV_FONT_DEFAULT, 0);
    lv_obj_set_flex_grow(body, 1);

    lv_obj_t *controls = lv_obj_create(notification_overlay);
    lv_obj_set_size(controls, lv_pct(100), 70);
    lv_obj_set_style_bg_opa(controls, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(controls, 0, 0);
    lv_obj_set_style_pad_all(controls, 2, 0);
    lv_obj_set_flex_flow(controls, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(
        controls, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER,
        LV_FLEX_ALIGN_CENTER
    );
    for (std::size_t index = 0; index < notification_buttons.count; ++index) {
        const auto &button = notification_buttons.items[index];
        lv_obj_t *action_button = lv_button_create(controls);
        lv_obj_set_size(action_button, 190, 64);
        lv_obj_set_style_bg_color(action_button, lv_color_hex(0x75579b), 0);
        lv_obj_add_event_cb(
            action_button, activate_notification_button, LV_EVENT_CLICKED,
            const_cast<char *>(button.entity_id.c_str())
        );
        lv_obj_t *action_label = lv_label_create(action_button);
        lv_label_set_text(action_label, button.label.c_str());
        style_high_contrast_text(action_label);
        lv_obj_center(action_label);
    }
    lv_obj_t *dismiss = lv_button_create(controls);
    lv_obj_set_size(dismiss, 220, 64);
    lv_obj_set_style_bg_color(
        dismiss,
        lv_color_hex(notification.emergency ? 0xa83b37 : 0x238f83),
        0
    );
    lv_obj_add_event_cb(dismiss, close_notification_overlay, LV_EVENT_CLICKED, nullptr);
    lv_obj_t *label = lv_label_create(dismiss);
    lv_label_set_text(label, "Dismiss");
    style_high_contrast_text(label);
    lv_obj_center(label);
    if (notification.timeout_seconds > 0) {
        notification_timer = lv_timer_create(
            expire_notification, notification.timeout_seconds * 1000, nullptr
        );
        lv_timer_set_repeat_count(notification_timer, 1);
    }
}

}  // namespace

}  // namespace roomhub::board
