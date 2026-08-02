#include "esp_log.h"

#include "roomhub/voice_session.hpp"

namespace {
constexpr char kTag[] = "roomhub_endpoint";
}

extern "C" void app_main(void)
{
    const roomhub::voice::SessionConfig config{
        .silence_timeout_ms = 800,
        .maximum_capture_ms = 12000,
    };
    roomhub::voice::VoiceSession session(config);

    ESP_LOGI(kTag, "RoomHub endpoint firmware starting");
    ESP_LOGI(kTag, "Board profile: M5Stack Tab5");
    ESP_LOGI(kTag, "On-device wake model: wn9_jarvis_tts");
    ESP_LOGI(
        kTag,
        "Privacy state: %s; network audio allowed: %s",
        roomhub::voice::to_string(session.state()),
        session.may_stream_audio() ? "yes" : "no"
    );

    // Hardware capture and transport are composed in the next milestone.
    // Until then this application cannot open a network audio session.
}
