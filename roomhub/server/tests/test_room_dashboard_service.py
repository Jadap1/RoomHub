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
            "media_players": [],
        })

    def test_media_players_are_separate_from_dashboard_entities(self):
        entity = Entity(
            entity_id="media_player.bedroom",
            entity_type="media_player",
            name="Bedroom speaker",
            area_id="kitchen",
        )
        entity_registry.entities[entity.entity_id] = entity
        entity_registry.states[entity.entity_id] = EntityState(
            state="playing",
            attributes={
                "media_title": "Test track",
                "volume_level": 0.35,
                "source_list": ["Music", "Radio"],
                "ignored": "not sent",
            },
        )

        snapshot = RoomDashboardService().snapshot("kitchen")

        self.assertEqual(snapshot["entities"], [])
        self.assertEqual(snapshot["media_players"][0]["entity_id"], entity.entity_id)
        self.assertNotIn(
            "ignored",
            snapshot["media_players"][0]["state"]["attributes"],
        )

    def test_snapshot_includes_extended_controls_and_compact_attributes(self):
        entity_types = (
            "climate", "fan", "cover", "scene", "script", "lock", "button",
            "input_button", "input_boolean", "number", "input_number", "select",
            "input_select",
        )
        for entity_type in entity_types:
            entity_id = f"{entity_type}.test"
            entity_registry.entities[entity_id] = Entity(
                entity_id=entity_id,
                entity_type=entity_type,
                name=entity_type.title(),
                area_id="kitchen",
            )
            entity_registry.states[entity_id] = EntityState(
                state="on",
                attributes={
                    "hvac_modes": ["off", "heat"],
                    "percentage": 50,
                    "current_position": 75,
                    "min": 0,
                    "max": 100,
                    "step": 5,
                    "options": ["Auto", "Eco"],
                    "ignored": "not sent",
                },
            )

        snapshot = RoomDashboardService().snapshot("kitchen")

        self.assertEqual(
            {item["entity_type"] for item in snapshot["entities"]},
            set(entity_types),
        )
        for item in snapshot["entities"]:
            self.assertNotIn("ignored", item["state"]["attributes"])

    def test_snapshot_omits_endpoint_exclusions(self):
        for entity_id in ("light.ceiling", "light.bedside"):
            entity_registry.entities[entity_id] = Entity(
                entity_id=entity_id,
                entity_type="light",
                name=entity_id.split(".")[1].title(),
                area_id="kitchen",
            )

        snapshot = RoomDashboardService().snapshot(
            "kitchen", excluded_entity_ids={"light.bedside"}
        )

        self.assertEqual(
            [item["entity_id"] for item in snapshot["entities"]],
            ["light.ceiling"],
        )

    def test_snapshot_orders_and_marks_favourites(self):
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

        snapshot = RoomDashboardService().snapshot(
            "kitchen",
            entity_preferences={
                "light.ceiling": {"position": 0, "pinned": False},
                "light.lamp": {"position": 1, "pinned": True},
            },
        )

        self.assertEqual(
            [item["entity_id"] for item in snapshot["entities"]],
            ["light.lamp", "light.ceiling"],
        )
        self.assertTrue(snapshot["entities"][0]["pinned"])

    def test_legacy_endpoint_uses_six_entity_compatibility_snapshot(self):
        service = RoomDashboardService()
        self.assertEqual(service.maximum_entities_for_firmware("0.4.2"), 6)
        self.assertEqual(service.maximum_entities_for_firmware("0.5.0"), 30)
        self.assertEqual(service.maximum_entities_for_firmware(None), 6)

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
