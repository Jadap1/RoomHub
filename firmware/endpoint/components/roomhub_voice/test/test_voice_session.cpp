#include "roomhub/voice_session.hpp"
#include "unity.h"

using roomhub::voice::SessionAction;
using roomhub::voice::SessionConfig;
using roomhub::voice::SessionState;
using roomhub::voice::VoiceSession;
using roomhub::voice::has_action;

TEST_CASE("audio is private until wake word detection", "[voice]")
{
    VoiceSession session;
    TEST_ASSERT_EQUAL(
        static_cast<int>(SessionState::waiting_for_wake_word),
        static_cast<int>(session.state())
    );
    TEST_ASSERT_FALSE(session.may_stream_audio());
    TEST_ASSERT_EQUAL(
        static_cast<int>(SessionAction::none),
        static_cast<int>(session.on_voice_activity(100))
    );

    const auto action = session.on_wake_word_detected(200);
    TEST_ASSERT_TRUE(
        has_action(action, SessionAction::begin_audio_stream)
    );
    TEST_ASSERT_TRUE(session.may_stream_audio());
}

TEST_CASE("local silence ends command capture", "[voice]")
{
    VoiceSession session(SessionConfig{
        .silence_timeout_ms = 800,
        .maximum_capture_ms = 12000,
    });
    session.on_wake_word_detected(1000);
    session.on_voice_activity(1200);

    TEST_ASSERT_EQUAL(
        static_cast<int>(SessionAction::none),
        static_cast<int>(session.on_tick(1999))
    );
    const auto action = session.on_tick(2000);
    TEST_ASSERT_TRUE(
        has_action(action, SessionAction::end_audio_stream)
    );
    TEST_ASSERT_FALSE(session.may_stream_audio());
    TEST_ASSERT_EQUAL(
        static_cast<int>(SessionState::awaiting_response),
        static_cast<int>(session.state())
    );
}

TEST_CASE("capture timeout limits transmitted audio", "[voice]")
{
    VoiceSession session(SessionConfig{
        .silence_timeout_ms = 20000,
        .maximum_capture_ms = 12000,
    });
    session.on_wake_word_detected(500);
    session.on_voice_activity(12499);

    const auto action = session.on_tick(12500);
    TEST_ASSERT_TRUE(
        has_action(action, SessionAction::end_audio_stream)
    );
    TEST_ASSERT_FALSE(session.may_stream_audio());
}

TEST_CASE("failures restore private idle state", "[voice]")
{
    VoiceSession session;
    session.on_wake_word_detected(0);

    const auto action = session.on_failure();
    TEST_ASSERT_TRUE(
        has_action(action, SessionAction::abort_audio_stream)
    );
    TEST_ASSERT_FALSE(session.may_stream_audio());
    TEST_ASSERT_EQUAL(
        static_cast<int>(SessionState::waiting_for_wake_word),
        static_cast<int>(session.state())
    );
}
