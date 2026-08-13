import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.models.endpoint import Endpoint
from app.services.camera_snapshot_service import (
    CameraSnapshotService,
    CameraSnapshotTimeout,
    CameraSnapshotUnavailable,
)


JPEG = b"\xff\xd8snapshot\xff\xd9"


class CameraSnapshotServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_sends_command_and_returns_uploaded_jpeg(self):
        service = CameraSnapshotService(timeout=1)
        endpoint = Endpoint(
            device_id="panel", device_name="Panel", room="Bedroom",
            capabilities=["camera"], connected=True,
        )

        async def send(endpoint_id, message):
            payload = message["payload"]
            service.upload(
                endpoint_id, payload["request_id"], payload["upload_token"], JPEG
            )
            return True

        with patch("app.services.camera_snapshot_service.registry.get", return_value=endpoint), patch(
            "app.services.camera_snapshot_service.manager.get", return_value=object()
        ), patch(
            "app.services.camera_snapshot_service.manager.send", new=AsyncMock(side_effect=send)
        ) as sender:
            image = await service.capture("panel")

        self.assertEqual(image, JPEG)
        self.assertEqual(sender.await_args.args[1]["type"], "camera.capture")
        self.assertNotIn(
            sender.await_args.args[1]["payload"]["upload_token"],
            sender.await_args.args[1]["payload"]["upload_path"],
        )

    async def test_offline_or_camera_less_endpoint_is_unavailable(self):
        service = CameraSnapshotService()
        endpoint = Endpoint(
            device_id="panel", device_name="Panel", room="Bedroom",
            capabilities=["display"], connected=True,
        )
        with patch("app.services.camera_snapshot_service.registry.get", return_value=endpoint):
            with self.assertRaises(CameraSnapshotUnavailable):
                await service.capture("panel")

    async def test_capture_timeout_cleans_up_pending_request(self):
        service = CameraSnapshotService(timeout=0.01)
        endpoint = Endpoint(
            device_id="panel", device_name="Panel", room="Bedroom",
            capabilities=["camera"], connected=True,
        )
        with patch("app.services.camera_snapshot_service.registry.get", return_value=endpoint), patch(
            "app.services.camera_snapshot_service.manager.get", return_value=object()
        ), patch(
            "app.services.camera_snapshot_service.manager.send", new=AsyncMock(return_value=True)
        ):
            with self.assertRaises(CameraSnapshotTimeout):
                await service.capture("panel")
        self.assertEqual(service._pending, {})

    def test_upload_rejects_invalid_token_and_non_jpeg(self):
        service = CameraSnapshotService()
        pending_type = __import__(
            "app.services.camera_snapshot_service", fromlist=["PendingSnapshot"]
        ).PendingSnapshot
        service._pending["request"] = pending_type("panel", "secret")
        with self.assertRaises(PermissionError):
            service.upload("panel", "request", "wrong", JPEG)
        with self.assertRaises(ValueError):
            service.upload("panel", "request", "secret", b"not-jpeg")
