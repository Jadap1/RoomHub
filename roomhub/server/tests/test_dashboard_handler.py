import unittest
from unittest.mock import AsyncMock, patch

from app.core.entity_registry import entity_registry
from app.core.entity_state import EntityState
from app.core.registry import registry
from app.handlers.dashboard_handler import handle_dashboard_activate
from app.models.endpoint import Endpoint
from app.models.entity import Entity


class DashboardHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        registry.endpoints = {}
        entity_registry.entities = {}
        entity_registry.states = {}
        registry.register(Endpoint(
            device_id="panel", device_name="Panel", room="Bedroom",
            area_id="bedroom", capabilities=["display"], connected=True,
        ))

    def tearDown(self):
        registry.endpoints = {}
        entity_registry.entities = {}
        entity_registry.states = {}

    async def test_switch_toggles_and_climate_power_follows_state(self):
        switch = Entity(
            entity_id="switch.lamp", entity_type="switch",
            name="Lamp", area_id="bedroom",
        )
        climate = Entity(
            entity_id="climate.radiator", entity_type="climate",
            name="Radiator", area_id="bedroom",
        )
        entity_registry.entities = {switch.entity_id: switch, climate.entity_id: climate}
        entity_registry.states[climate.entity_id] = EntityState(state="off")

        with patch("app.handlers.dashboard_handler.event_bus.publish", new=AsyncMock()) as publish:
            switch_result = await handle_dashboard_activate({
                "source": "panel", "payload": {"entity_id": switch.entity_id},
            })
            climate_result = await handle_dashboard_activate({
                "source": "panel", "payload": {"entity_id": climate.entity_id},
            })
            entity_registry.states[climate.entity_id] = EntityState(
                state="heat",
                attributes={
                    "temperature": 20.0,
                    "target_temp_step": 0.5,
                    "min_temp": 5.0,
                    "max_temp": 30.0,
                },
            )
            temperature_result = await handle_dashboard_activate({
                "source": "panel",
                "payload": {
                    "entity_id": climate.entity_id,
                    "action": "temperature_up",
                },
            })

        self.assertEqual(switch_result["payload"]["command"], "toggle")
        self.assertEqual(climate_result["payload"]["command"], "turn_on")
        self.assertEqual(temperature_result["payload"]["command"], "set_temperature")
        self.assertEqual(publish.await_args_list[2].args[0].data, {"temperature": 20.5})
        self.assertEqual(publish.await_count, 3)

    async def test_rejects_entity_from_another_area(self):
        entity_registry.entities["light.other"] = Entity(
            entity_id="light.other", entity_type="light",
            name="Other", area_id="kitchen",
        )
        result = await handle_dashboard_activate({
            "source": "panel", "payload": {"entity_id": "light.other"},
        })
        self.assertEqual(result["type"], "command.rejected")

    async def test_extended_device_actions_build_safe_commands(self):
        entities = (
            Entity(entity_id="light.main", entity_type="light", name="Main", area_id="bedroom"),
            Entity(entity_id="fan.ceiling", entity_type="fan", name="Fan", area_id="bedroom"),
            Entity(entity_id="cover.blind", entity_type="cover", name="Blind", area_id="bedroom"),
            Entity(entity_id="scene.relax", entity_type="scene", name="Relax", area_id="bedroom"),
        )
        entity_registry.entities = {entity.entity_id: entity for entity in entities}
        entity_registry.states["light.main"] = EntityState(
            state="on", attributes={"brightness": 250}
        )
        entity_registry.states["fan.ceiling"] = EntityState(
            state="on", attributes={"percentage": 95, "percentage_step": 10}
        )

        with patch(
            "app.handlers.dashboard_handler.event_bus.publish", new=AsyncMock()
        ) as publish:
            await handle_dashboard_activate({
                "source": "panel",
                "payload": {"entity_id": "light.main", "action": "brightness_up"},
            })
            await handle_dashboard_activate({
                "source": "panel",
                "payload": {"entity_id": "fan.ceiling", "action": "percentage_up"},
            })
            await handle_dashboard_activate({
                "source": "panel",
                "payload": {"entity_id": "cover.blind", "action": "cover_close"},
            })
            await handle_dashboard_activate({
                "source": "panel", "payload": {"entity_id": "scene.relax"},
            })

        events = [call.args[0] for call in publish.await_args_list]
        self.assertEqual(events[0].data, {"brightness": 255})
        self.assertEqual(events[1].data, {"percentage": 100})
        self.assertEqual(events[2].command, "close_cover")
        self.assertEqual(events[3].command, "turn_on")

    async def test_climate_mode_cycles_and_wrong_domain_is_rejected(self):
        climate = Entity(
            entity_id="climate.main", entity_type="climate",
            name="Climate", area_id="bedroom",
        )
        entity_registry.entities[climate.entity_id] = climate
        entity_registry.states[climate.entity_id] = EntityState(
            state="heat", attributes={"hvac_modes": ["off", "heat", "cool"]}
        )
        with patch(
            "app.handlers.dashboard_handler.event_bus.publish", new=AsyncMock()
        ) as publish:
            result = await handle_dashboard_activate({
                "source": "panel",
                "payload": {"entity_id": climate.entity_id, "action": "mode_next"},
            })
            rejected = await handle_dashboard_activate({
                "source": "panel",
                "payload": {"entity_id": climate.entity_id, "action": "cover_open"},
            })
        self.assertEqual(result["payload"]["command"], "set_hvac_mode")
        self.assertEqual(publish.await_args.args[0].data, {"hvac_mode": "cool"})
        self.assertEqual(rejected["type"], "command.rejected")


if __name__ == "__main__":
    unittest.main()
