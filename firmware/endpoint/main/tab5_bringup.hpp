#pragma once

namespace roomhub::board {

struct Tab5BringUpResult {
    bool display_ready = false;
    bool touch_ready = false;
    bool microphone_ready = false;
    bool speaker_ready = false;
};

Tab5BringUpResult initialize_tab5(bool endpoint_provisioned);

}  // namespace roomhub::board
