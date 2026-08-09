import asyncio
import unittest
from unittest.mock import patch

from app.core.event_bus import EventBus
from app.events.entity_events import (
    EntityDiscoveredEvent,
    EntityRemovedEvent,
    EntityStateChangedEvent,
)
from app.integrations.homeassistant.providers.entity_provider import HomeAssistantEntityProvider
from app.integrations.homeassistant.providers.registry_updates import HomeAssistantRegistryUpdates, REGISTRY_EVENT_TYPES
from app.integrations.homeassistant.providers.state_provider import HomeAssistantStateProvider
from app.integrations.homeassistant_config import EntityFilterConfig


class FakeEntityProvider:
    def __init__(self):
        self.discovered = []
        self.registry_syncs = 0

    def allows(self, entity_id):
        return entity_id.startswith("light.")

    async def publish_discovered(self, state):
        self.discovered.append(state)

    async def sync_registry(self):
        self.registry_syncs += 1


class FakeProvider:
    def __init__(self):
        self.syncs = 0

    async def sync(self):
        self.syncs += 1


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_entity_filter_and_effective_area(self):
        bus = EventBus()
        events = []

        async def capture(event):
            events.append(event)

        async def send_request(payload):
            return [
                {"entity_id": "light.direct", "device_id": "device-1", "area_id": "direct", "platform": "test", "entity_category": None},
                {"entity_id": "light.inherited", "device_id": "device-1", "area_id": None, "platform": "test", "entity_category": None},
            ]

        bus.subscribe(EntityDiscoveredEvent, capture)
        provider = HomeAssistantEntityProvider(
            EntityFilterConfig(mode="include", patterns=["light.*"]),
            send_request,
            lambda device_id: "inherited",
        )
        with patch("app.integrations.homeassistant.providers.entity_provider.event_bus", bus):
            await provider.sync_registry()
            await provider.publish_discovered({"entity_id": "light.direct", "state": "on", "attributes": {}})
            await provider.publish_discovered({"entity_id": "light.inherited", "state": "on", "attributes": {}})

        self.assertTrue(provider.allows("light.test"))
        self.assertFalse(provider.allows("switch.test"))
        self.assertEqual([event.area_id for event in events], ["direct", "inherited"])

    async def test_state_availability(self):
        bus = EventBus()
        events = []
        entity_provider = FakeEntityProvider()

        async def capture(event):
            events.append(event)

        async def send_request(payload):
            return None

        bus.subscribe(EntityStateChangedEvent, capture)
        provider = HomeAssistantStateProvider(entity_provider, send_request)
        with patch("app.integrations.homeassistant.providers.state_provider.event_bus", bus):
            await provider.publish_state({"entity_id": "light.test", "state": "unknown", "attributes": {"test": True}})

        self.assertEqual(len(entity_provider.discovered), 1)
        self.assertFalse(events[0].available)
        self.assertEqual(events[0].attributes, {"test": True})

    async def test_entity_registry_removal_is_published(self):
        bus = EventBus()
        removed = []
        responses = [
            [{"entity_id": "light.removed"}],
            []
        ]

        async def capture(event):
            removed.append(event.entity_id)

        async def send_request(payload):
            return responses.pop(0)

        bus.subscribe(EntityRemovedEvent, capture)
        provider = HomeAssistantEntityProvider(
            EntityFilterConfig(),
            send_request,
            lambda device_id: None
        )

        with patch(
            "app.integrations.homeassistant.providers."
            "entity_provider.event_bus",
            bus
        ):
            await provider.sync_registry()
            await provider.sync_registry()

        self.assertEqual(
            removed,
            ["light.removed"]
        )

    async def test_registry_updates_coalesce(self):
        floor = FakeProvider()
        area = FakeProvider()
        device = FakeProvider()
        entity = FakeEntityProvider()
        state_refreshes = 0
        subscriptions = []

        async def refresh_states():
            nonlocal state_refreshes
            state_refreshes += 1

        async def send_request(payload):
            subscriptions.append(payload)

        updates = HomeAssistantRegistryUpdates(floor, area, device, entity, refresh_states, send_request)
        await updates.subscribe()
        self.assertEqual({item["event_type"] for item in subscriptions}, REGISTRY_EVENT_TYPES)

        for event_type in ("area_registry_updated", "device_registry_updated", "entity_registry_updated"):
            await updates.handle_event({"event": {"event_type": event_type}})
        await asyncio.wait_for(updates._refresh_task, timeout=1)

        self.assertEqual((area.syncs, device.syncs, entity.registry_syncs), (1, 1, 1))
        self.assertEqual(state_refreshes, 1)

    async def test_registry_refresh_task_is_awaited_on_stop(self):
        started = asyncio.Event()
        release = asyncio.Event()

        class BlockingProvider(FakeProvider):
            async def sync(self):
                started.set()
                await release.wait()

        updates = HomeAssistantRegistryUpdates(
            BlockingProvider(),
            FakeProvider(),
            FakeProvider(),
            FakeEntityProvider(),
            lambda: asyncio.sleep(0),
            lambda payload: asyncio.sleep(0)
        )
        await updates.handle_event(
            {
                "event": {
                    "event_type": "floor_registry_updated"
                }
            }
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        task = updates._refresh_task

        await updates.stop()

        self.assertTrue(task.done())
        self.assertIsNone(updates._refresh_task)
        self.assertEqual(
            updates._pending_event_types,
            set()
        )
