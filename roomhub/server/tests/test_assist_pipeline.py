import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.integrations.homeassistant.assist_pipeline import (
    HomeAssistantAssistError,
    HomeAssistantSpeechToTextSession,
)


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = [json.dumps(message) for message in messages]
        self.sent = []
        self.closed = False

    async def recv(self):
        return self.messages.pop(0)

    async def send(self, message):
        self.sent.append(message)

    async def close(self):
        self.closed = True


def successful_messages(pipelines=None):
    if pipelines is None:
        pipelines = [
            {"id": "pipeline-1", "name": "RoomHub Local"}
        ]
    return [
        {"type": "auth_required"},
        {"type": "auth_ok"},
        {
            "id": 1,
            "type": "result",
            "success": True,
            "result": {
                "pipelines": pipelines
            },
        },
        {"id": 2, "type": "result", "success": True},
        {
            "id": 2,
            "type": "event",
            "event": {
                "type": "run-start",
                "data": {
                    "runner_data": {"stt_binary_handler_id": 7}
                },
            },
        },
        {
            "id": 2,
            "type": "event",
            "event": {"type": "stt-start", "data": {}},
        },
    ]


class AssistPipelineTests(unittest.IsolatedAsyncioTestCase):
    def make_session(self, websocket):
        async def connect(*args, **kwargs):
            return websocket

        settings = SimpleNamespace(
            websocket_url="ws://example/api/websocket",
            access_token="secret",
        )
        patcher = patch(
            "app.integrations.homeassistant.assist_pipeline."
            "get_homeassistant_connection_settings",
            return_value=settings,
        )
        self.addCleanup(patcher.stop)
        patcher.start()
        return HomeAssistantSpeechToTextSession(
            pipeline_name="RoomHub Local",
            connect_websocket=connect,
        )

    async def test_streams_pcm_and_returns_transcript(self):
        websocket = FakeWebSocket(
            successful_messages()
            + [
                {
                    "id": 2,
                    "type": "event",
                    "event": {
                        "type": "stt-end",
                        "data": {
                            "stt_output": {
                                "text": "turn on the kitchen light"
                            }
                        },
                    },
                },
                {
                    "id": 2,
                    "type": "event",
                    "event": {"type": "run-end", "data": {}},
                },
            ]
        )
        session = self.make_session(websocket)

        await session.start()
        await session.send_audio(b"\x01\x02")
        transcript = await session.finish()

        self.assertEqual(transcript, "turn on the kitchen light")
        self.assertEqual(websocket.sent[-2], b"\x07\x01\x02")
        self.assertEqual(websocket.sent[-1], b"\x07")
        self.assertTrue(websocket.closed)

        run_request = json.loads(websocket.sent[2])
        self.assertEqual(run_request["start_stage"], "stt")
        self.assertEqual(run_request["end_stage"], "stt")
        self.assertEqual(run_request["pipeline"], "pipeline-1")
        self.assertEqual(run_request["input"]["sample_rate"], 16000)

    async def test_requires_exactly_one_named_pipeline(self):
        websocket = FakeWebSocket(successful_messages(pipelines=[]))
        session = self.make_session(websocket)

        with self.assertRaisesRegex(
            HomeAssistantAssistError,
            "found 0",
        ):
            await session.start()

        self.assertTrue(websocket.closed)

    async def test_rejects_invalid_pcm_frames(self):
        websocket = FakeWebSocket(successful_messages())
        session = self.make_session(websocket)
        await session.start()

        with self.assertRaisesRegex(ValueError, "must not be empty"):
            await session.send_audio(b"")
        with self.assertRaisesRegex(ValueError, "even byte length"):
            await session.send_audio(b"\x00")
        with self.assertRaisesRegex(ValueError, "64 KiB"):
            await session.send_audio(b"\x00\x00" * 32769)

        await session.abort()

    async def test_reports_pipeline_error(self):
        messages = successful_messages()[:-2]
        messages.append({
            "id": 2,
            "type": "event",
            "event": {
                "type": "error",
                "data": {"code": "stt-failed", "message": "No speech"},
            },
        })
        websocket = FakeWebSocket(messages)
        session = self.make_session(websocket)

        with self.assertRaisesRegex(HomeAssistantAssistError, "No speech"):
            await session.start()

        self.assertTrue(websocket.closed)
