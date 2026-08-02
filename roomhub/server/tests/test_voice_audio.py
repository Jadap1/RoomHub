import unittest

from app.integrations.homeassistant.assist_pipeline import (
    HomeAssistantAssistError,
)
from app.services.voice_audio_service import VoiceAudioConnection


VALID_AUDIO = {
    "sample_rate": 16000,
    "channels": 1,
    "format": "pcm_s16le",
}


class FakeSession:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.started = False
        self.aborted = False
        self.frames = []
        self.transcript = "turn on the kitchen light"
        self.finish_error = None

    async def start(self):
        self.started = True

    async def send_audio(self, audio):
        self.frames.append(audio)

    async def finish(self):
        if self.finish_error:
            raise self.finish_error
        return self.transcript

    async def abort(self):
        self.aborted = True


class FakeIntentService:
    def __init__(self):
        self.calls = []

    async def handle_transcript(self, transcript, endpoint_id=None):
        self.calls.append((transcript, endpoint_id))
        return {
            "version": "1.0",
            "type": "voice.intent.accepted",
            "payload": {"status": "accepted"},
        }


class VoiceAudioTests(unittest.IsolatedAsyncioTestCase):
    def make_connection(self):
        self.sessions = []

        def factory(sample_rate):
            session = FakeSession(sample_rate)
            self.sessions.append(session)
            return session

        self.intent_service = FakeIntentService()
        return VoiceAudioConnection(factory, self.intent_service)

    async def test_streams_post_wake_audio_into_safe_intent_path(self):
        connection = self.make_connection()

        ready = await connection.start(VALID_AUDIO)
        frame_response = await connection.send_audio(b"\x01\x02")
        response = await connection.finish("kitchen-panel")

        self.assertEqual(ready["type"], "voice.audio.ready")
        self.assertIsNone(frame_response)
        self.assertEqual(self.sessions[0].frames, [b"\x01\x02"])
        self.assertEqual(
            self.intent_service.calls,
            [("turn on the kitchen light", "kitchen-panel")],
        )
        self.assertEqual(response["type"], "voice.intent.accepted")
        self.assertEqual(
            response["payload"]["transcript"],
            "turn on the kitchen light",
        )

    async def test_rejects_audio_without_active_wake_session(self):
        connection = self.make_connection()

        response = await connection.send_audio(b"\x01\x02")

        self.assertEqual(response["type"], "voice.audio.rejected")
        self.assertEqual(response["payload"]["reason"], "no_active_session")

    async def test_rejects_unsupported_audio_and_parallel_session(self):
        connection = self.make_connection()

        invalid = await connection.start({**VALID_AUDIO, "sample_rate": 8000})
        ready = await connection.start(VALID_AUDIO)
        duplicate = await connection.start(VALID_AUDIO)

        self.assertEqual(
            invalid["payload"]["reason"],
            "unsupported_audio_format",
        )
        self.assertEqual(ready["type"], "voice.audio.ready")
        self.assertEqual(
            duplicate["payload"]["reason"],
            "session_already_active",
        )
        await connection.close()

    async def test_cancel_aborts_session(self):
        connection = self.make_connection()
        await connection.start(VALID_AUDIO)

        response = await connection.cancel()

        self.assertEqual(response["type"], "voice.audio.cancelled")
        self.assertTrue(self.sessions[0].aborted)

    async def test_transcription_failure_does_not_reach_intent_service(self):
        connection = self.make_connection()
        await connection.start(VALID_AUDIO)
        self.sessions[0].finish_error = HomeAssistantAssistError("no speech")

        response = await connection.finish("kitchen-panel")

        self.assertEqual(response["type"], "voice.audio.failed")
        self.assertEqual(self.intent_service.calls, [])
