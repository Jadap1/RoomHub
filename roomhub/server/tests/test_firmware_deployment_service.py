import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.core.registry import registry
from app.models.endpoint import Endpoint
from app.services.firmware_deployment_service import FirmwareDeploymentService
from app.services.firmware_service import FirmwareManifest


class FirmwareDeploymentServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.audit_patch = patch(
            "app.services.firmware_deployment_service.firmware_audit.record"
        )
        self.audit_patch.start()
        registry.endpoints = {
            "panel": Endpoint(
                device_id="panel", device_name="Panel", firmware_version="0.7.1",
                room="Bedroom", capabilities=["display"], connected=True,
            )
        }

    def tearDown(self):
        self.audit_patch.stop()
        registry.endpoints = {}

    async def test_tracks_acknowledgement_progress_and_completion(self):
        service = FirmwareDeploymentService(acknowledgement_timeout=0.02)
        manifest = FirmwareManifest(version="0.7.2", size=123, sha256="a" * 64)
        with patch("app.services.firmware_deployment_service.manager.get", return_value=object()), patch(
            "app.services.firmware_deployment_service.manager.send", new=AsyncMock(return_value=True)
        ):
            deployment = await service.deploy("panel", manifest)
        updated = service.update("panel", {
            "request_id": deployment["request_id"],
            "status": "downloading",
            "progress": 42,
        })
        self.assertEqual(updated["progress"], 42)
        service.mark_running("panel", "0.7.2")
        self.assertEqual(service.get("panel")["status"], "completed")

    async def test_marks_missing_acknowledgement(self):
        service = FirmwareDeploymentService(acknowledgement_timeout=0.01)
        manifest = FirmwareManifest(version="0.7.2", size=123, sha256="a" * 64)
        with patch("app.services.firmware_deployment_service.manager.get", return_value=object()), patch(
            "app.services.firmware_deployment_service.manager.send", new=AsyncMock(return_value=True)
        ):
            await service.deploy("panel", manifest)
            await asyncio.sleep(0.03)
        self.assertEqual(service.get("panel")["status"], "unacknowledged")


if __name__ == "__main__":
    unittest.main()
