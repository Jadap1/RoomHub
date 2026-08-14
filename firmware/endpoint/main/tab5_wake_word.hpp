#pragma once

#include "esp_codec_dev.h"
#include "roomhub/voice_session.hpp"

namespace roomhub::board {

bool start_tab5_wake_word_detector(
    esp_codec_dev_handle_t microphone,
    roomhub::voice::VoiceSession &session
);
void set_tab5_microphone_muted(bool muted);
bool tab5_microphone_muted();

}  // namespace roomhub::board
