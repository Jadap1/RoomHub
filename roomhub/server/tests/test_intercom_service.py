import unittest
from unittest.mock import AsyncMock, patch

from app.core.connection_manager import manager
from app.core.registry import registry
from app.models.endpoint import Endpoint
from app.services.intercom_service import IntercomService


class IntercomServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        registry.endpoints = {}
        manager.connections = {}
        self.source = Endpoint(
            device_id="source", device_name="Source panel", room="Kitchen",
            capabilities=["microphone", "speaker"], connected=True,
            state={"controls": {"microphone_muted": False}},
        )
        self.target = Endpoint(
            device_id="target", device_name="Target panel", room="Bedroom",
            capabilities=["microphone", "speaker"], connected=True,
        )
        registry.endpoints = {"source": self.source, "target": self.target}
        manager.connections = {"source": object(), "target": object()}
        self.service = IntercomService()

    def tearDown(self):
        registry.endpoints = {}
        manager.connections = {}

    async def test_routes_pcm_only_during_reserved_session(self):
        with patch.object(manager, "send", new=AsyncMock(return_value=True)) as send, \
             patch.object(manager, "send_bytes", new=AsyncMock(return_value=True)) as send_bytes:
            ready = await self.service.start("source", {
                "target_endpoint_id": "target", "sample_rate": 16000,
                "channels": 1, "format": "pcm_s16le",
            })
            self.assertEqual(ready["type"], "intercom.ready")
            self.assertTrue(self.service.is_transmitting("source"))
            await self.service.send_audio("source", b"\x01\x00\x02\x00")
            ended = await self.service.stop("source")

        self.assertEqual(send.await_args_list[0].args[0], "target")
        send_bytes.assert_awaited_once_with("target", b"\x01\x00\x02\x00")
        self.assertEqual(ended["type"], "intercom.ended")
        self.assertFalse(self.service.is_transmitting("source"))

    async def test_rejects_muted_busy_and_invalid_audio(self):
        self.source.state["controls"]["microphone_muted"] = True
        muted = await self.service.start("source", {
            "target_endpoint_id": "target", "sample_rate": 16000,
            "channels": 1, "format": "pcm_s16le",
        })
        self.assertEqual(muted["payload"]["reason"], "source_microphone_unavailable")
        self.source.state["controls"]["microphone_muted"] = False

        with patch.object(manager, "send", new=AsyncMock(return_value=True)):
            await self.service.start("source", {
                "target_endpoint_id": "target", "sample_rate": 16000,
                "channels": 1, "format": "pcm_s16le",
            })
            busy = await self.service.start("target", {
                "target_endpoint_id": "source", "sample_rate": 16000,
                "channels": 1, "format": "pcm_s16le",
            })
            invalid = await self.service.send_audio("source", b"odd")

        self.assertEqual(busy["payload"]["reason"], "endpoint_busy")
        self.assertEqual(invalid["payload"]["reason"], "invalid_audio_frame")

    async def test_disconnect_releases_peer(self):
        with patch.object(manager, "send", new=AsyncMock(return_value=True)) as send:
            await self.service.start("source", {
                "target_endpoint_id": "target", "sample_rate": 16000,
                "channels": 1, "format": "pcm_s16le",
            })
            await self.service.close_endpoint("target")
        self.assertFalse(self.service.is_transmitting("source"))
        self.assertEqual(send.await_args.args[0], "source")
        self.assertEqual(send.await_args.args[1]["payload"]["reason"], "peer_disconnected")

    async def test_target_can_reject_when_speaker_is_busy(self):
        with patch.object(manager, "send", new=AsyncMock(return_value=True)) as send:
            await self.service.start("source", {
                "target_endpoint_id": "target", "sample_rate": 16000,
                "channels": 1, "format": "pcm_s16le",
            })
            response = await self.service.target_status(
                "target", {"status": "rejected"}
            )
        self.assertEqual(response["payload"]["status"], "rejected")
        self.assertEqual(send.await_args.args[0], "source")
        self.assertEqual(send.await_args.args[1]["type"], "intercom.rejected")
        self.assertFalse(self.service.is_transmitting("source"))


if __name__ == "__main__":
    unittest.main()
