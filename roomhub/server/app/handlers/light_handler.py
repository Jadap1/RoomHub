from ..core.event_bus import event_bus
from ..events.entity_events import EntityCommandEvent


async def handle_light_toggle(message):

    entity_id = message["payload"].get(
        "entity_id"
    )

    if not entity_id:

        return {
            "version": "1.0",
            "type": "error",
            "payload": {
                "message": "entity_id is required"
            }
        }


    event = EntityCommandEvent(
        entity_id=entity_id,
        command="toggle"
    )


    await event_bus.publish(event)


    return {
        "version": "1.0",
        "type": "command.accepted",
        "payload": {
            "entity_id": entity_id,
            "command": "toggle"
        }
    }