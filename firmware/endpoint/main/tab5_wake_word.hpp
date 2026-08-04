#pragma once

#include "esp_codec_dev.h"

namespace roomhub::board {

bool start_tab5_wake_word_detector(esp_codec_dev_handle_t microphone);

}  // namespace roomhub::board
