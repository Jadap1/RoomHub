import unittest

from app.events.entity_events import EntityCommandEvent
from app.integrations.homeassistant.commands import HomeAssistantCommands


class CommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_entity_command_builds_service_call(self):
        requests = []

        async def send_request(payload):
            requests.append(payload)

        commands = HomeAssistantCommands(send_request)
        await commands.handle_entity_command(EntityCommandEvent(
            entity_id="light.kitchen",
            command="turn_on",
            data={"brightness": 100},
        ))
        self.assertEqual(requests, [{
            "type": "call_service",
            "domain": "light",
            "service": "turn_on",
            "service_data": {"brightness": 100},
            "target": {"entity_id": "light.kitchen"},
        }])

    async def test_empty_service_data_is_preserved(self):
        requests = []

        async def send_request(payload):
            requests.append(payload)

        commands = HomeAssistantCommands(send_request)
        await commands.call_service("switch", "turn_off", "switch.test")
        self.assertEqual(requests[0]["service_data"], {})
