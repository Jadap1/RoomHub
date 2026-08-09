import unittest
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from app.services.audio_command_service import (
    AudioCommandService,
    AudioPlayRequest,
)
from app.handlers.audio_handler import handle_audio_status


class AudioCommandServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_notification_audio_to_connected_endpoint(self):
        service = AudioCommandService()
        request = AudioPlayRequest(
            request_id="doorbell-1",
            url="https://roomhub.local/audio/doorbell.mp3",
        )
        with (
            patch("app.services.audio_command_service.manager.get", return_value=object()),
            patch("app.services.audio_command_service.manager.send", new=AsyncMock()) as send,
        ):
            result = await service.play("kitchen-panel", request)
        self.assertEqual(result["status"], "sent")
        message = send.await_args.args[1]
        self.assertEqual(message["type"], "audio.play")
        self.assertEqual(message["payload"]["priority"], "notification")

    async def test_rejects_unavailable_endpoint_without_sending(self):
        service = AudioCommandService()
        request = AudioPlayRequest(url="https://roomhub.local/test.mp3")
        with (
            patch("app.services.audio_command_service.manager.get", return_value=None),
            patch("app.services.audio_command_service.manager.send", new=AsyncMock()) as send,
        ):
            result = await service.play("missing", request)
        self.assertEqual(result["status"], "unavailable")
        send.assert_not_awaited()

    def test_validates_audio_url_format_and_priority(self):
        with self.assertRaises(ValidationError):
            AudioPlayRequest(url="file:///tmp/test.mp3")
        with self.assertRaises(ValidationError):
            AudioPlayRequest(
                url="https://roomhub.local/test.mp3",
                priority="background",
            )

    async def test_audio_status_is_acknowledged(self):
        response = await handle_audio_status({
            "type": "audio.status",
            "source": "kitchen-panel",
            "payload": {
                "request_id": "doorbell-1",
                "status": "completed",
            },
        })
        self.assertEqual(response["type"], "audio.status.ack")
        self.assertEqual(response["payload"]["status"], "completed")
