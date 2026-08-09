from ..core.entity_registry import entity_registry
from ..core.event_bus import event_bus
from ..core.registry import registry
from ..events.entity_events import EntityCommandEvent


async def handle_dashboard_activate(message: dict) -> dict:
    endpoint_id = message.get("source")
    payload = message.get("payload") or {}
    entity_id = payload.get("entity_id")
    endpoint = registry.get(endpoint_id) if isinstance(endpoint_id, str) else None
    entity = entity_registry.get(entity_id) if isinstance(entity_id, str) else None
    if (
        endpoint is None
        or entity is None
        or endpoint.area_id is None
        or entity.area_id != endpoint.area_id
        or entity.entity_type not in {"light", "switch", "climate"}
    ):
        return {
            "version": "1.0",
            "type": "command.rejected",
            "payload": {"reason": "entity_not_controllable_in_endpoint_area"},
        }

    command = "toggle"
    if entity.entity_type == "climate":
        state = entity_registry.get_state(entity.entity_id) or {}
        command = "turn_on" if state.get("state") == "off" else "turn_off"
    await event_bus.publish(EntityCommandEvent(
        entity_id=entity.entity_id,
        command=command,
    ))
    return {
        "version": "1.0",
        "type": "command.accepted",
        "payload": {"entity_id": entity.entity_id, "command": command},
    }
