#pragma once

#include "esp_codec_dev.h"

namespace roomhub::board {

struct Tab5BringUpResult {
    bool display_ready = false;
    bool touch_ready = false;
    bool microphone_ready = false;
    bool speaker_ready = false;
    esp_codec_dev_handle_t microphone = nullptr;
};

Tab5BringUpResult initialize_tab5(bool endpoint_provisioned);
void show_tab5_wake_word_listening();
void show_tab5_wake_word_detected();

}  // namespace roomhub::board
