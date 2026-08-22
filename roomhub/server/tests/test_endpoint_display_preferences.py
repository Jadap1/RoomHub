import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.core import database
from app.core.registry import registry
from app.models.endpoint import Endpoint
from app.services.endpoint_display_preferences_service import (
    EndpointDisplayPreferencesService,
)


class EndpointDisplayPreferencesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        registry.endpoints = {}

    def tearDown(self):
        registry.endpoints = {}

    async def test_defaults_preserve_existing_display_behaviour(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(database, "DATABASE", Path(directory) / "roomhub.db"):
                database.initialise_database()
                self.assertEqual(EndpointDisplayPreferencesService().get("panel"), {
                    "tap_to_wake": True,
                    "wake_on_voice": True,
                    "sleep_timeout_seconds": 0,
                    "dashboard_layout": "grouped",
                })

    async def test_preferences_persist_and_refresh_connected_display(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(database, "DATABASE", Path(directory) / "roomhub.db"):
                database.initialise_database()
                registry.register(Endpoint(
                    device_id="panel",
                    device_name="Panel",
                    room="Kitchen",
                    area_id="kitchen",
                    capabilities=["display"],
                    connected=True,
                ))
                service = EndpointDisplayPreferencesService()
                with patch(
                    "app.services.endpoint_display_preferences_service."
                    "room_dashboard_service.send",
                    new=AsyncMock(),
                ) as send:
                    result = await service.save(
                        "panel",
                        tap_to_wake=False,
                        wake_on_voice=True,
                        sleep_timeout_seconds=300,
                        dashboard_layout="direct",
                    )
                self.assertEqual(result["status"], "saved")
                self.assertEqual(service.get("panel"), {
                    "tap_to_wake": False,
                    "wake_on_voice": True,
                    "sleep_timeout_seconds": 300,
                    "dashboard_layout": "direct",
                })
                send.assert_awaited_once_with("panel")


if __name__ == "__main__":
    unittest.main()
