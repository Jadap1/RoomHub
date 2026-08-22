import asyncio
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
        self.service = IntercomService(ringing_timeout_seconds=0.02)

    def tearDown(self):
        self.service.reset()
        registry.endpoints = {}
        manager.connections = {}

    @staticmethod
    def request(target: str = "target") -> dict:
        return {
            "target_endpoint_id": target,
            "sample_rate": 16000,
            "channels": 1,
            "format": "pcm_s16le",
        }

    async def _ring_and_accept(self, send: AsyncMock) -> str:
        ringing = await self.service.start("source", self.request())
        self.assertEqual(ringing["type"], "intercom.ringing")
        call_id = ringing["payload"]["call_id"]
        active = await self.service.target_status(
            "target", {"call_id": call_id, "status": "accepted"}
        )
        self.assertEqual(active["type"], "intercom.active")
        self.assertEqual(send.await_args.args[0], "source")
        self.assertEqual(send.await_args.args[1]["type"], "intercom.active")
        return call_id

    async def test_ringing_accept_and_bidirectional_pcm(self):
        with (
            patch.object(manager, "send", new=AsyncMock(return_value=True)) as send,
            patch.object(
                manager, "send_bytes", new=AsyncMock(return_value=True)
            ) as send_bytes,
        ):
            call_id = await self._ring_and_accept(send)
            self.assertTrue(self.service.is_transmitting("source"))
            self.assertTrue(self.service.is_transmitting("target"))
            await self.service.send_audio("source", b"\x01\x00\x02\x00")
            await self.service.send_audio("target", b"\x03\x00\x04\x00")
            ended = await self.service.stop(
                "target", {"call_id": call_id}, "completed"
            )

        self.assertEqual(
            send_bytes.await_args_list[0].args,
            ("target", b"\x01\x00\x02\x00"),
        )
        self.assertEqual(
            send_bytes.await_args_list[1].args,
            ("source", b"\x03\x00\x04\x00"),
        )
        self.assertEqual(ended["type"], "intercom.ended")
        self.assertFalse(self.service.has_session("source"))

    async def test_target_declines_and_call_id_is_required(self):
        with patch.object(manager, "send", new=AsyncMock(return_value=True)) as send:
            ringing = await self.service.start("source", self.request())
            call_id = ringing["payload"]["call_id"]
            stale = await self.service.target_status(
                "target", {"call_id": "wrong", "status": "accepted"}
            )
            self.assertEqual(stale["payload"]["reason"], "no_incoming_call")
            declined = await self.service.target_status(
                "target", {"call_id": call_id, "status": "declined"}
            )

        self.assertEqual(declined["payload"]["reason"], "declined")
        self.assertEqual(send.await_args.args[0], "source")
        self.assertEqual(send.await_args.args[1]["type"], "intercom.rejected")
        self.assertFalse(self.service.has_session("source"))

    async def test_ringing_timeout_notifies_both_endpoints(self):
        with patch.object(manager, "send", new=AsyncMock(return_value=True)) as send:
            await self.service.start("source", self.request())
            await asyncio.sleep(0.04)

        notifications = [(call.args[0], call.args[1]) for call in send.await_args_list]
        self.assertIn(
            ("target", unittest.mock.ANY), notifications
        )
        target_messages = [message for endpoint, message in notifications if endpoint == "target"]
        source_messages = [message for endpoint, message in notifications if endpoint == "source"]
        self.assertEqual(target_messages[-1]["payload"]["reason"], "missed")
        self.assertEqual(source_messages[-1]["payload"]["reason"], "no_answer")
        self.assertFalse(self.service.has_session("source"))

    async def test_rejects_muted_busy_and_invalid_audio(self):
        self.source.state["controls"]["microphone_muted"] = True
        muted = await self.service.start("source", self.request())
        self.assertEqual(muted["payload"]["reason"], "source_audio_unavailable")
        self.source.state["controls"]["microphone_muted"] = False

        with patch.object(manager, "send", new=AsyncMock(return_value=True)) as send:
            call_id = await self._ring_and_accept(send)
            busy = await self.service.start("target", self.request("source"))
            invalid = await self.service.send_audio("source", b"odd")

        self.assertEqual(busy["payload"]["reason"], "endpoint_busy")
        self.assertEqual(invalid["payload"]["reason"], "invalid_audio_frame")
        self.assertFalse(self.service.has_session("source"))
        self.assertIsInstance(call_id, str)

    async def test_disconnect_releases_peer(self):
        with patch.object(manager, "send", new=AsyncMock(return_value=True)) as send:
            await self.service.start("source", self.request())
            await self.service.close_endpoint("target")
        self.assertFalse(self.service.has_session("source"))
        self.assertEqual(send.await_args.args[0], "source")
        self.assertEqual(send.await_args.args[1]["payload"]["reason"], "peer_disconnected")


if __name__ == "__main__":
    unittest.main()
