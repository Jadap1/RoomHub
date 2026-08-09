import json
import unittest

from app.core.area_registry import area_registry
from app.core.entity_registry import entity_registry
from app.core.entity_state import EntityState
from app.models.area import Area
from app.models.entity import Entity
from app.services.room_dashboard_service import RoomDashboardService


class RoomDashboardServiceTests(unittest.TestCase):
    def setUp(self):
        area_registry.areas = {
            "kitchen": Area(area_id="kitchen", name="Kitchen"),
            "study": Area(area_id="study", name="Study"),
        }
        entity_registry.entities = {}
        entity_registry.states = {}

    def tearDown(self):
        area_registry.areas = {}
        entity_registry.entities = {}
        entity_registry.states = {}

    def test_snapshot_contains_only_supported_area_entities(self):
        for entity in (
            Entity(entity_id="light.main", entity_type="light", name="Main", area_id="kitchen"),
            Entity(entity_id="switch.fan", entity_type="switch", name="Fan", area_id="kitchen"),
            Entity(entity_id="sensor.temp", entity_type="sensor", name="Temperature", area_id="kitchen"),
            Entity(entity_id="light.study", entity_type="light", name="Desk", area_id="study"),
        ):
            entity_registry.entities[entity.entity_id] = entity
            entity_registry.states[entity.entity_id] = EntityState(state="on")

        snapshot = RoomDashboardService().snapshot("kitchen")

        self.assertEqual(snapshot["area_name"], "Kitchen")
        self.assertEqual(
            [item["entity_id"] for item in snapshot["entities"]],
            ["light.main", "switch.fan"],
        )
        self.assertEqual(
            [item["action"] for item in snapshot["entities"]],
            ["activate", "activate"],
        )

    def test_unassigned_snapshot_is_empty(self):
        self.assertEqual(RoomDashboardService().snapshot(None), {
            "area_id": None,
            "area_name": "Unassigned",
            "entities": [],
        })

    def test_snapshot_is_capped_and_compacts_state_attributes(self):
        for index in range(40):
            entity = Entity(
                entity_id=f"light.test_{index}",
                entity_type="light",
                name=f"Test {index}",
                area_id="kitchen",
            )
            entity_registry.entities[entity.entity_id] = entity
            entity_registry.states[entity.entity_id] = EntityState(
                state="on",
                attributes={"brightness": 128, "large_ignored_value": "x" * 4096},
            )

        snapshot = RoomDashboardService().snapshot("kitchen")

        self.assertEqual(len(snapshot["entities"]), 30)
        self.assertEqual(
            snapshot["entities"][0]["state"]["attributes"],
            {"brightness": 128},
        )
        self.assertLess(len(json.dumps(snapshot).encode()), 8192)


if __name__ == "__main__":
    unittest.main()
