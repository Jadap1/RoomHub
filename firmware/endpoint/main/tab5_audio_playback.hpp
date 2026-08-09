#pragma once

#include <string>
#include <atomic>

#include "esp_codec_dev.h"

namespace roomhub::board {

enum class PlaybackResult { completed, cancelled, failed };

PlaybackResult play_tab5_mp3_url(
    esp_codec_dev_handle_t speaker,
    const std::string &url,
    const std::atomic_bool *cancel_requested = nullptr
);

}  // namespace roomhub::board
