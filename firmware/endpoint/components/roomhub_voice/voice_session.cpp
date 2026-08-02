#include "roomhub/voice_session.hpp"

namespace roomhub::voice {

VoiceSession::VoiceSession(SessionConfig config) : config_(config) {}

SessionState VoiceSession::state() const
{
    return state_;
}

bool VoiceSession::may_stream_audio() const
{
    return state_ == SessionState::capturing_command;
}

SessionAction VoiceSession::on_wake_word_detected(std::uint64_t now_ms)
{
    if (state_ != SessionState::waiting_for_wake_word) {
        return SessionAction::none;
    }

    capture_started_ms_ = now_ms;
    last_voice_activity_ms_ = now_ms;
    state_ = SessionState::capturing_command;
    return SessionAction::begin_audio_stream;
}

SessionAction VoiceSession::on_voice_activity(std::uint64_t now_ms)
{
    if (state_ != SessionState::capturing_command) {
        return SessionAction::none;
    }

    last_voice_activity_ms_ = now_ms;
    return SessionAction::none;
}

SessionAction VoiceSession::on_tick(std::uint64_t now_ms)
{
    if (state_ != SessionState::capturing_command) {
        return SessionAction::none;
    }

    const bool capture_expired = (
        now_ms - capture_started_ms_
        >= config_.maximum_capture_ms
    );
    const bool silence_expired = (
        now_ms - last_voice_activity_ms_
        >= config_.silence_timeout_ms
    );

    if (capture_expired || silence_expired) {
        return finish_capture();
    }
    return SessionAction::none;
}

SessionAction VoiceSession::finish_capture()
{
    state_ = SessionState::awaiting_response;
    return SessionAction::end_audio_stream;
}

SessionAction VoiceSession::on_response_ready()
{
    if (state_ != SessionState::awaiting_response) {
        return SessionAction::none;
    }

    state_ = SessionState::playing_response;
    return SessionAction::begin_playback;
}

SessionAction VoiceSession::on_playback_finished()
{
    if (state_ != SessionState::playing_response) {
        return SessionAction::none;
    }

    state_ = SessionState::waiting_for_wake_word;
    return SessionAction::stop_playback;
}

SessionAction VoiceSession::on_failure()
{
    SessionAction actions = SessionAction::none;
    if (state_ == SessionState::capturing_command) {
        actions = SessionAction::abort_audio_stream;
    } else if (state_ == SessionState::playing_response) {
        actions = SessionAction::stop_playback;
    }
    state_ = SessionState::waiting_for_wake_word;
    return actions;
}

const char *to_string(SessionState state)
{
    switch (state) {
    case SessionState::waiting_for_wake_word:
        return "waiting_for_wake_word";
    case SessionState::capturing_command:
        return "capturing_command";
    case SessionState::awaiting_response:
        return "awaiting_response";
    case SessionState::playing_response:
        return "playing_response";
    }
    return "unknown";
}

}  // namespace roomhub::voice
