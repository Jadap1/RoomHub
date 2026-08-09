#pragma once

#include <cstdint>
#include <string>

#include "esp_codec_dev.h"
#include "roomhub/audio_scheduler.hpp"

namespace roomhub::board {

enum class AudioPlaybackState { unknown, queued, playing, completed, interrupted, failed };
using AudioEventCallback = void (*)(
    const std::string &request_id,
    AudioPlaybackState state
);

bool start_tab5_audio_service(esp_codec_dev_handle_t speaker);
void set_tab5_audio_event_callback(AudioEventCallback callback);
std::uint32_t submit_tab5_audio(
    const std::string &request_id,
    const std::string &url,
    const std::string &mime_type,
    roomhub::audio::Priority priority,
    bool retain_final_state = false
);
bool cancel_tab5_audio(std::uint32_t token);
bool cancel_tab5_audio(const std::string &request_id);
AudioPlaybackState tab5_audio_state(std::uint32_t token);
bool tab5_audio_output_active();
void interrupt_tab5_audio_for_voice_capture();

}  // namespace roomhub::board
