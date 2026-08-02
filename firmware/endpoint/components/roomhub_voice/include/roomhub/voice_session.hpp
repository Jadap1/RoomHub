#pragma once

#include <cstdint>

namespace roomhub::voice {

enum class SessionState {
    waiting_for_wake_word,
    capturing_command,
    awaiting_response,
    playing_response,
};

enum class SessionAction : std::uint32_t {
    none = 0,
    begin_audio_stream = 1U << 0,
    end_audio_stream = 1U << 1,
    abort_audio_stream = 1U << 2,
    begin_playback = 1U << 3,
    stop_playback = 1U << 4,
};

constexpr SessionAction operator|(SessionAction left, SessionAction right)
{
    return static_cast<SessionAction>(
        static_cast<std::uint32_t>(left)
        | static_cast<std::uint32_t>(right)
    );
}

constexpr bool has_action(SessionAction actions, SessionAction action)
{
    return (
        static_cast<std::uint32_t>(actions)
        & static_cast<std::uint32_t>(action)
    ) != 0;
}

struct SessionConfig {
    std::uint32_t silence_timeout_ms = 800;
    std::uint32_t maximum_capture_ms = 12000;
};

class VoiceSession {
public:
    explicit VoiceSession(SessionConfig config = {});

    SessionState state() const;
    bool may_stream_audio() const;

    SessionAction on_wake_word_detected(std::uint64_t now_ms);
    SessionAction on_voice_activity(std::uint64_t now_ms);
    SessionAction on_tick(std::uint64_t now_ms);
    SessionAction on_response_ready();
    SessionAction on_playback_finished();
    SessionAction on_failure();

private:
    SessionConfig config_;
    SessionState state_ = SessionState::waiting_for_wake_word;
    std::uint64_t capture_started_ms_ = 0;
    std::uint64_t last_voice_activity_ms_ = 0;

    SessionAction finish_capture();
};

const char *to_string(SessionState state);

}  // namespace roomhub::voice
