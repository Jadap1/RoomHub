import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.core import database
from app.core.area_registry import area_registry
from app.core.registry import registry
from app.models.area import Area
from app.models.endpoint import Endpoint
from app.services.endpoint_assignment_service import EndpointAssignmentService
from app.services.notification_service import NotificationRequest, NotificationService
from app.integrations.homeassistant.tts_pipeline import SpeechOutput


class FakeTtsClient:
    async def synthesize(self, text):
        return SpeechOutput(
            url="http://homeassistant.local:8123/api/tts/test.mp3",
            mime_type="audio/mpeg",
        )


class NotificationServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        registry.endpoints = {}

    def tearDown(self):
        registry.endpoints = {}
        area_registry.areas = {}
        area_registry.areas = {}

    async def test_routes_area_notification_to_displays_and_connected_speakers(self):
        registry.register(Endpoint(
            device_id="kitchen-panel",
            device_name="Kitchen Panel",
            room="Kitchen",
            area_id="kitchen",
            capabilities=["speaker"],
            connected=True,
        ))
        registry.register(Endpoint(
            device_id="kitchen-display",
            device_name="Kitchen Display",
            room="Kitchen",
            area_id="kitchen",
            capabilities=["display"],
            connected=True,
        ))
        registry.register(Endpoint(
            device_id="offline-speaker",
            device_name="Offline",
            room="Kitchen",
            area_id="kitchen",
            capabilities=["speaker"],
            connected=False,
        ))
        service = NotificationService(tts_factory=FakeTtsClient)
        with patch(
            "app.services.notification_service.audio_command_service.play",
            new=AsyncMock(return_value={"status": "sent"}),
        ) as play, patch(
            "app.services.notification_service.manager.send",
            new=AsyncMock(return_value=True),
        ) as send:
            result = await service.notify(NotificationRequest(
                text="Dinner is ready",
                title="Dinner",
                area_id="kitchen",
            ))
        self.assertEqual(
            set(result["targets"]), {"kitchen-panel", "kitchen-display"}
        )
        self.assertEqual(play.await_args.args[0], "kitchen-panel")
        self.assertEqual(play.await_args.args[1].priority, "notification")
        self.assertEqual(send.await_args.args[0], "kitchen-display")
        self.assertEqual(
            send.await_args.args[1]["payload"]["title"], "Dinner"
        )

    async def test_delivery_status_tracks_each_endpoint(self):
        registry.register(Endpoint(
            device_id="panel",
            device_name="Panel",
            room="Kitchen",
            area_id="kitchen",
            capabilities=["speaker"],
            connected=True,
        ))
        service = NotificationService(tts_factory=FakeTtsClient)
        with patch(
            "app.services.notification_service.audio_command_service.play",
            new=AsyncMock(return_value={"status": "sent"}),
        ):
            delivery = await service.notify(NotificationRequest(
                text="Test",
                endpoint_id="panel",
            ))
        delivery_id = delivery["delivery_id"]
        service.update_status(delivery_id, "panel", "playing")
        self.assertEqual(service.get(delivery_id)["status"], "playing")
        service.update_status(delivery_id, "panel", "completed")
        self.assertEqual(service.get(delivery_id)["status"], "completed")

    def test_title_validation(self):
        self.assertEqual(NotificationRequest(text="Test", endpoint_id="panel").title, "RoomHub")
        with self.assertRaises(ValueError):
            NotificationRequest(text="Test", title=" ", endpoint_id="panel")

    async def test_unavailable_target_does_not_synthesize(self):
        tts = AsyncMock()
        service = NotificationService(tts_factory=lambda: tts)
        result = await service.notify(NotificationRequest(
            text="Test",
            area_id="empty-room",
        ))
        self.assertEqual(result["status"], "unavailable")
        tts.synthesize.assert_not_awaited()

    def test_requires_exactly_one_target(self):
        with self.assertRaises(ValueError):
            NotificationRequest(text="Test")
        with self.assertRaises(ValueError):
            NotificationRequest(
                text="Test",
                endpoint_id="panel",
                area_id="kitchen",
            )

    async def test_endpoint_area_assignment_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "roomhub.db"
            with patch.object(database, "DATABASE", database_path):
                database.initialise_database()
                area_registry.areas = {
                    "kitchen": Area(area_id="kitchen", name="Kitchen")
                }
                registry.register(Endpoint(
                    device_id="panel",
                    device_name="Panel",
                    room="Unassigned",
                    capabilities=["speaker"],
                    connected=True,
                ))
                service = EndpointAssignmentService()
                result = await service.assign("panel", "kitchen")
                self.assertEqual(result["status"], "assigned")
                self.assertEqual(service.get_area_id("panel"), "kitchen")
                self.assertEqual(registry.get("panel").room, "Kitchen")

                recovered = Endpoint(
                    device_id="recovered-panel",
                    device_name="Recovered",
                    room="Unassigned",
                    area_id="kitchen",
                    capabilities=["display"],
                )
                service.apply(recovered)
                self.assertEqual(service.get_area_id("recovered-panel"), "kitchen")
                self.assertEqual(recovered.room, "Kitchen")


if __name__ == "__main__":
    unittest.main()
