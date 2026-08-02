from .entity_registry import entity_registry
from .event_bus import event_bus
from ..events.entity_events import (
    EntityCommandEvent,
    EntityDiscoveredEvent,
    EntityRemovedEvent,
    EntityStateChangedEvent,
)
from ..integrations.registry import homeassistant

from .area_registry import area_registry
from .device_registry import device_registry
from .floor_registry import floor_registry

from ..events.entity_events import (
    AreaDiscoveredEvent,
    AreaRemovedEvent,
    DeviceDiscoveredEvent,
    DeviceRemovedEvent,
    FloorDiscoveredEvent,
    FloorRemovedEvent,
)

def register_event_subscriptions(
    homeassistant_connector=homeassistant
) -> None:

    event_bus.subscribe(
        EntityCommandEvent,
        homeassistant_connector.handle_entity_command
    )

    event_bus.subscribe(
        EntityDiscoveredEvent,
        entity_registry.handle_entity_discovered
    )

    event_bus.subscribe(
        EntityStateChangedEvent,
        entity_registry.handle_state_changed
    )
    event_bus.subscribe(
        EntityRemovedEvent,
        entity_registry.handle_entity_removed
    )
    event_bus.subscribe(
        FloorDiscoveredEvent,
        floor_registry.handle_discovered
    )
    event_bus.subscribe(
        FloorRemovedEvent,
        floor_registry.handle_removed
    )

    event_bus.subscribe(
        AreaDiscoveredEvent,
        area_registry.handle_discovered
    )
    event_bus.subscribe(
        AreaRemovedEvent,
        area_registry.handle_removed
    )

    event_bus.subscribe(
        DeviceDiscoveredEvent,
        device_registry.handle_discovered
    )
    event_bus.subscribe(
        DeviceRemovedEvent,
        device_registry.handle_removed
    )
