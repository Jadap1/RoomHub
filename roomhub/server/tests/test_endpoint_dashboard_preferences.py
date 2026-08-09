import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.core import database
from app.core.entity_registry import entity_registry
from app.core.registry import registry
from app.models.endpoint import Endpoint
from app.models.entity import Entity
from app.services.endpoint_dashboard_preferences_service import (
    EndpointDashboardPreferencesService,
)


class EndpointDashboardPreferencesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        registry.endpoints = {}
        entity_registry.entities = {}

    def tearDown(self):
        registry.endpoints = {}
        entity_registry.entities = {}

    async def test_exclusions_are_persistent_and_area_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roomhub.db"
            with patch.object(database, "DATABASE", path):
                database.initialise_database()
                registry.register(Endpoint(
                    device_id="panel",
                    device_name="Panel",
                    room="Kitchen",
                    area_id="kitchen",
                    capabilities=["display"],
                    connected=True,
                ))
                for entity in (
                    Entity(
                        entity_id="light.main",
                        entity_type="light",
                        name="Main",
                        area_id="kitchen",
                    ),
                    Entity(
                        entity_id="update.main",
                        entity_type="update",
                        name="Firmware",
                        area_id="kitchen",
                    ),
                    Entity(
                        entity_id="switch.study",
                        entity_type="switch",
                        name="Study",
                        area_id="study",
                    ),
                ):
                    entity_registry.entities[entity.entity_id] = entity

                service = EndpointDashboardPreferencesService()
                with patch(
                    "app.services.room_dashboard_service."
                    "room_dashboard_service.send",
                    new=AsyncMock(),
                ) as send:
                    result = await service.replace_exclusions(
                        "panel", {"light.main"}
                    )

                self.assertEqual(result["status"], "saved")
                self.assertEqual(
                    service.excluded_entity_ids("panel"), {"light.main"}
                )
                self.assertEqual(service.eligible_entities("panel"), [{
                    "entity_id": "light.main",
                    "entity_type": "light",
                    "name": "Main",
                    "visible": False,
                    "pinned": False,
                }])
                send.assert_awaited_once_with("panel")

    async def test_order_and_favourites_are_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roomhub.db"
            with patch.object(database, "DATABASE", path):
                database.initialise_database()
                registry.register(Endpoint(
                    device_id="panel",
                    device_name="Panel",
                    room="Kitchen",
                    area_id="kitchen",
                    capabilities=["display"],
                    connected=True,
                ))
                for entity_id, name in (
                    ("light.ceiling", "Ceiling"),
                    ("light.lamp", "Lamp"),
                ):
                    entity_registry.entities[entity_id] = Entity(
                        entity_id=entity_id,
                        entity_type="light",
                        name=name,
                        area_id="kitchen",
                    )

                service = EndpointDashboardPreferencesService()
                with patch(
                    "app.services.room_dashboard_service."
                    "room_dashboard_service.send",
                    new=AsyncMock(),
                ):
                    result = await service.replace_exclusions(
                        "panel",
                        set(),
                        ["light.ceiling", "light.lamp"],
                        {"light.lamp"},
                    )

                self.assertEqual(result["status"], "saved")
                entities = service.eligible_entities("panel")
                self.assertEqual(
                    [item["entity_id"] for item in entities],
                    ["light.lamp", "light.ceiling"],
                )
                self.assertTrue(entities[0]["pinned"])

    async def test_rejects_noneligible_entity_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roomhub.db"
            with patch.object(database, "DATABASE", path):
                database.initialise_database()
                registry.register(Endpoint(
                    device_id="panel",
                    device_name="Panel",
                    room="Kitchen",
                    area_id="kitchen",
                    capabilities=["display"],
                ))
                result = await EndpointDashboardPreferencesService().replace_exclusions(
                    "panel", {"update.firmware"}
                )
                self.assertEqual(result["status"], "invalid_entities")


if __name__ == "__main__":
    unittest.main()
