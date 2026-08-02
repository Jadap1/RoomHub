import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.integrations.homeassistant.tts_pipeline import (
    HomeAssistantTextToSpeechClient,
    HomeAssistantTextToSpeechError,
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


def messages(output=None):
    if output is None:
        output = {
            "token": "audio-token",
            "url": "/api/tts_proxy/audio.mp3",
            "mime_type": "audio/mpeg",
        }
    return [
        {"type": "auth_required"},
        {"type": "auth_ok"},
        {
            "id": 1,
            "type": "result",
            "success": True,
            "result": {
                "pipelines": [
                    {"id": "pipeline-1", "name": "RoomHub Local"}
                ]
            },
        },
        {"id": 2, "type": "result", "success": True},
        {
            "id": 2,
            "type": "event",
            "event": {"type": "run-start", "data": {}},
        },
        {
            "id": 2,
            "type": "event",
            "event": {"type": "tts-start", "data": {}},
        },
        {
            "id": 2,
            "type": "event",
            "event": {
                "type": "tts-end",
                "data": {"tts_output": output},
            },
        },
        {
            "id": 2,
            "type": "event",
            "event": {"type": "run-end", "data": {}},
        },
    ]


class TextToSpeechPipelineTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, websocket):
        async def connect(*args, **kwargs):
            return websocket

        settings = SimpleNamespace(
            websocket_url="ws://example/api/websocket",
            access_token="secret",
        )
        patcher = patch(
            "app.integrations.homeassistant.tts_pipeline."
            "get_homeassistant_connection_settings",
            return_value=settings,
        )
        self.addCleanup(patcher.stop)
        patcher.start()
        public_url_patcher = patch(
            "app.integrations.homeassistant.tts_pipeline."
            "get_homeassistant_public_url",
            return_value="http://homeassistant.local:8123",
        )
        self.addCleanup(public_url_patcher.stop)
        public_url_patcher.start()
        return HomeAssistantTextToSpeechClient(
            pipeline_name="RoomHub Local",
            connect_websocket=connect,
        )

    async def test_returns_piper_audio_metadata(self):
        websocket = FakeWebSocket(messages())
        client = self.make_client(websocket)

        output = await client.synthesize("Done.")

        self.assertEqual(output.mime_type, "audio/mpeg")
        self.assertIn("tts_proxy", output.url)
        self.assertTrue(output.url.startswith("http://homeassistant.local:8123/"))
        self.assertEqual(output.token, "audio-token")
        request = json.loads(websocket.sent[2])
        self.assertEqual(request["start_stage"], "tts")
        self.assertEqual(request["end_stage"], "tts")
        self.assertEqual(request["input"], {"text": "Done."})
        self.assertTrue(websocket.closed)

    async def test_rejects_missing_audio_metadata(self):
        websocket = FakeWebSocket(messages(output={"token": "token"}))
        client = self.make_client(websocket)

        with self.assertRaisesRegex(
            HomeAssistantTextToSpeechError,
            "audio URL",
        ):
            await client.synthesize("Done.")

        self.assertTrue(websocket.closed)

    async def test_rejects_empty_text_without_connecting(self):
        websocket = FakeWebSocket([])
        client = self.make_client(websocket)

        with self.assertRaisesRegex(ValueError, "must not be empty"):
            await client.synthesize("  ")

        self.assertEqual(websocket.sent, [])
