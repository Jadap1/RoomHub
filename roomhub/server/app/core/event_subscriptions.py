from .event_bus import event_bus
from ..events.entity_events import EntityCommandEvent
from ..integrations.registry import homeassistant


def register_event_subscriptions() -> None:

    event_bus.subscribe(
        EntityCommandEvent,
        homeassistant.handle_entity_command
    )