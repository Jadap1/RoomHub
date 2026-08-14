#pragma once

#include <array>
#include <string>
#include <vector>

#include "esp_codec_dev.h"

namespace roomhub::board {

struct Tab5BringUpResult {
    bool display_ready = false;
    bool touch_ready = false;
    bool microphone_ready = false;
    bool speaker_ready = false;
    esp_codec_dev_handle_t microphone = nullptr;
    esp_codec_dev_handle_t speaker = nullptr;
};

struct DashboardEntity {
    std::string entity_id;
    std::string entity_type;
    std::string name;
    std::string state;
    std::string hvac_action;
    bool available = true;
    bool actionable = false;
    bool pinned = false;
    float current_temperature = 0.0F;
    float target_temperature = 0.0F;
    int brightness = 0;
    int percentage = 0;
    int current_position = 0;
    bool has_current_temperature = false;
    bool has_target_temperature = false;
    bool has_brightness = false;
    bool has_percentage = false;
    bool has_current_position = false;
};

struct MediaPlayer {
    std::string entity_id;
    std::string name;
    std::string state;
    std::string media_title;
    std::string media_artist;
    std::string source;
    bool available = true;
    bool muted = false;
    int volume_percent = 0;
};

using DashboardAction = void (*)(const char *entity_id, const char *action, int value);
using MicrophoneMuteAction = void (*)();
using NotificationAction = void (*)(const char *delivery_id, const char *status);
using NotificationButtonAction = void (*)(
    const char *delivery_id, const char *entity_id
);

struct NotificationButton {
    std::string label;
    std::string entity_id;
};

struct NotificationButtons {
    std::array<NotificationButton, 2> items;
    std::size_t count = 0;
};

Tab5BringUpResult initialize_tab5(bool endpoint_provisioned);
void show_tab5_wake_word_listening();
void show_tab5_wake_word_detected();
void show_tab5_microphone_muted();
void set_tab5_microphone_mute_action(MicrophoneMuteAction action);
void show_tab5_wireless_scan(unsigned int network_count);
void show_tab5_wireless_connected();
void show_tab5_wireless_retrying(unsigned int delay_seconds);
void show_tab5_wireless_failed();
void show_tab5_roomhub_connecting();
void show_tab5_roomhub_retrying(unsigned int delay_seconds);
void show_tab5_roomhub_registered();
void show_tab5_firmware_updating(unsigned int percent);
void show_tab5_firmware_failed();
void show_tab5_firmware_restarting();
bool set_tab5_screen_on(bool screen_on);
void show_tab5_dashboard(
    const std::string &area_name,
    const std::vector<DashboardEntity> &entities,
    const std::vector<MediaPlayer> &media_players,
    DashboardAction action
);
void show_tab5_notification(
    const std::string &delivery_id,
    const std::string &title,
    const std::string &text,
    bool emergency,
    unsigned int timeout_seconds,
    bool queue,
    const NotificationButtons &buttons,
    NotificationAction action,
    NotificationButtonAction button_action
);

}  // namespace roomhub::board
