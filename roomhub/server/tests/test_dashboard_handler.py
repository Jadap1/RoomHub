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


if __name__ == "__main__":
    unittest.main()
