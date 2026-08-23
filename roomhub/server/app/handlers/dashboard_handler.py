from ..core.entity_registry import entity_registry
from ..core.event_bus import event_bus
from ..core.registry import registry
from ..events.entity_events import EntityCommandEvent
from ..services.room_dashboard_service import MANAGEABLE_ENTITY_TYPES


async def handle_dashboard_activate(message: dict) -> dict:
    endpoint_id = message.get("source")
    payload = message.get("payload") or {}
    entity_id = payload.get("entity_id")
    action = payload.get("action", "activate")
    value = payload.get("value")
    endpoint = registry.get(endpoint_id) if isinstance(endpoint_id, str) else None
    entity = entity_registry.get(entity_id) if isinstance(entity_id, str) else None
    if (
        endpoint is None
        or entity is None
        or endpoint.area_id is None
        or entity.area_id != endpoint.area_id
        or entity.entity_type not in MANAGEABLE_ENTITY_TYPES
    ):
        return {
            "version": "1.0",
            "type": "command.rejected",
            "payload": {"reason": "entity_not_controllable_in_endpoint_area"},
        }

    if action not in {
        "activate", "temperature_down", "temperature_up", "mode_next",
        "brightness_down", "brightness_up", "brightness_set",
        "percentage_down", "percentage_up",
        "cover_open", "cover_stop", "cover_close",
        "number_down", "number_up", "number_set", "select_next",
        "media_play_pause", "media_previous", "media_next",
        "media_volume_set", "media_source_next",
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
    elif action in {"brightness_down", "brightness_up", "brightness_set"}:
        if entity.entity_type != "light":
            return _rejected("brightness_action_requires_light")
        if action == "brightness_set":
            if not isinstance(value, (int, float)):
                return _rejected("brightness_value_required")
            brightness = value
        else:
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
    elif action in {"number_down", "number_up", "number_set"}:
        if entity.entity_type not in {"number", "input_number"}:
            return _rejected("number_action_requires_number")
        if action == "number_set":
            if not isinstance(value, (int, float)):
                return _rejected("number_value_required")
            target = float(value)
        else:
            try:
                current = float(state.get("state"))
            except (TypeError, ValueError):
                return _rejected("number_value_unavailable")
            step = attributes.get("step", 1)
            step = step if isinstance(step, (int, float)) and step > 0 else 1
            target = current + step if action == "number_up" else current - step
        minimum = attributes.get("min", target)
        maximum = attributes.get("max", target)
        if isinstance(minimum, (int, float)):
            target = max(minimum, target)
        if isinstance(maximum, (int, float)):
            target = min(maximum, target)
        command = "set_value"
        data = {"value": target}
    elif action == "select_next":
        if entity.entity_type not in {"select", "input_select"}:
            return _rejected("select_action_requires_select")
        command = "select_next"
    elif action.startswith("media_"):
        if entity.entity_type != "media_player":
            return _rejected("media_action_requires_media_player")
        if action == "media_play_pause":
            command = "media_play_pause"
        elif action == "media_previous":
            command = "media_previous_track"
        elif action == "media_next":
            command = "media_next_track"
        elif action == "media_volume_set":
            if not isinstance(value, (int, float)):
                return _rejected("media_volume_value_required")
            command = "volume_set"
            data = {"volume_level": max(0.0, min(1.0, value / 100.0))}
        else:
            sources = attributes.get("source_list") or []
            sources = [source for source in sources if isinstance(source, str)]
            if not sources:
                return _rejected("media_sources_unavailable")
            current_source = attributes.get("source")
            next_index = (
                (sources.index(current_source) + 1) % len(sources)
                if current_source in sources else 0
            )
            command = "select_source"
            data = {"source": sources[next_index]}
    elif entity.entity_type == "climate":
        command = "turn_on" if state.get("state") == "off" else "turn_off"
    elif entity.entity_type in {"scene", "script"}:
        command = "turn_on"
    elif entity.entity_type in {"button", "input_button"}:
        command = "press"
    elif entity.entity_type == "lock":
        command = "unlock" if state.get("state") == "locked" else "lock"
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
