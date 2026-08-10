from ..core.entity_registry import entity_registry
from ..core.event_bus import event_bus
from ..core.registry import registry
from ..events.entity_events import EntityCommandEvent
from ..services.room_dashboard_service import SUPPORTED_ENTITY_TYPES


async def handle_dashboard_activate(message: dict) -> dict:
    endpoint_id = message.get("source")
    payload = message.get("payload") or {}
    entity_id = payload.get("entity_id")
    action = payload.get("action", "activate")
    endpoint = registry.get(endpoint_id) if isinstance(endpoint_id, str) else None
    entity = entity_registry.get(entity_id) if isinstance(entity_id, str) else None
    if (
        endpoint is None
        or entity is None
        or endpoint.area_id is None
        or entity.area_id != endpoint.area_id
        or entity.entity_type not in SUPPORTED_ENTITY_TYPES
    ):
        return {
            "version": "1.0",
            "type": "command.rejected",
            "payload": {"reason": "entity_not_controllable_in_endpoint_area"},
        }

    if action not in {
        "activate", "temperature_down", "temperature_up", "mode_next",
        "brightness_down", "brightness_up", "percentage_down", "percentage_up",
        "cover_open", "cover_stop", "cover_close",
    }:
        return {
            "version": "1.0",
            "type": "command.rejected",
            "payload": {"reason": "unsupported_dashboard_action"},
        }

    command = "toggle"
    data = {}
    state = entity_registry.get_state(entity.entity_id) or {}
    attributes = state.get("attributes") or {}
    if action in {"temperature_down", "temperature_up"}:
        if entity.entity_type != "climate":
            return {
                "version": "1.0",
                "type": "command.rejected",
                "payload": {"reason": "temperature_action_requires_climate"},
            }
        target = attributes.get("temperature")
        if not isinstance(target, (int, float)):
            return {
                "version": "1.0",
                "type": "command.rejected",
                "payload": {"reason": "target_temperature_unavailable"},
            }
        step = attributes.get("target_temp_step", 0.5)
        step = step if isinstance(step, (int, float)) and step > 0 else 0.5
        target += step if action == "temperature_up" else -step
        minimum = attributes.get("min_temp", target)
        maximum = attributes.get("max_temp", target)
        target = max(minimum, min(maximum, target))
        command = "set_temperature"
        data = {"temperature": target}
    elif action in {"brightness_down", "brightness_up"}:
        if entity.entity_type != "light":
            return _rejected("brightness_action_requires_light")
        brightness = attributes.get("brightness", 0)
        brightness = brightness if isinstance(brightness, (int, float)) else 0
        brightness += 26 if action == "brightness_up" else -26
        command = "turn_on"
        data = {"brightness": int(max(1, min(255, brightness)))}
    elif action == "mode_next":
        if entity.entity_type != "climate":
            return _rejected("mode_action_requires_climate")
        modes = attributes.get("hvac_modes") or []
        modes = [mode for mode in modes if isinstance(mode, str)]
        if not modes:
            return _rejected("hvac_modes_unavailable")
        current = state.get("state")
        next_index = (modes.index(current) + 1) % len(modes) if current in modes else 0
        command = "set_hvac_mode"
        data = {"hvac_mode": modes[next_index]}
    elif action in {"percentage_down", "percentage_up"}:
        if entity.entity_type != "fan":
            return _rejected("percentage_action_requires_fan")
        percentage = attributes.get("percentage", 0)
        percentage = percentage if isinstance(percentage, (int, float)) else 0
        step = attributes.get("percentage_step", 10)
        step = step if isinstance(step, (int, float)) and step > 0 else 10
        percentage += step if action == "percentage_up" else -step
        command = "set_percentage"
        data = {"percentage": int(max(0, min(100, percentage)))}
    elif action.startswith("cover_"):
        if entity.entity_type != "cover":
            return _rejected("cover_action_requires_cover")
        command = {
            "cover_open": "open_cover",
            "cover_stop": "stop_cover",
            "cover_close": "close_cover",
        }[action]
    elif entity.entity_type == "climate":
        command = "turn_on" if state.get("state") == "off" else "turn_off"
    elif entity.entity_type in {"scene", "script"}:
        command = "turn_on"
    await event_bus.publish(EntityCommandEvent(
        entity_id=entity.entity_id,
        command=command,
        data=data,
    ))
    return {
        "version": "1.0",
        "type": "command.accepted",
        "payload": {"entity_id": entity.entity_id, "command": command},
    }


def _rejected(reason: str) -> dict:
    return {
        "version": "1.0",
        "type": "command.rejected",
        "payload": {"reason": reason},
    }
