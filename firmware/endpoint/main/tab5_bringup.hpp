#pragma once

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

Tab5BringUpResult initialize_tab5(bool endpoint_provisioned);
void show_tab5_wake_word_listening();
void show_tab5_wake_word_detected();
void show_tab5_wireless_scan(unsigned int network_count);
void show_tab5_wireless_connected();
void show_tab5_wireless_failed();

}  // namespace roomhub::board
