from .entity_registry import entity_registry
from .event_bus import event_bus
from ..events.entity_events import (
    EntityCommandEvent,
    EntityDiscoveredEvent,
    EntityStateChangedEvent,
)
from ..integrations.registry import homeassistant


def register_event_subscriptions() -> None:

    event_bus.subscribe(
        EntityCommandEvent,
        homeassistant.handle_entity_command
    )

    event_bus.subscribe(
        EntityDiscoveredEvent,
        entity_registry.handle_entity_discovered
    )

    event_bus.subscribe(
        EntityStateChangedEvent,
        entity_registry.handle_state_changed
    )