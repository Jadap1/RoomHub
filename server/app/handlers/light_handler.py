from ..core.entity_registry import entity_registry


async def handle_light_toggle(message):

    entity_id = message["payload"].get(
        "entity_id"
    )

    entity = entity_registry.get(
        entity_id
    )


    if not entity:

        return {
            "version": "1.0",
            "type": "error",
            "payload": {
                "message": f"Unknown entity: {entity_id}"
            }
        }


    if entity.state == "off":

        entity.state = "on"

    else:

        entity.state = "off"
        
    entity_registry.save(entity) 


    print(
        "[LIGHT COMMAND]",
        entity.entity_id,
        "->",
        entity.state
    )


    return {
        "version": "1.0",
        "type": "light.state_changed",
        "payload": {
            "entity_id": entity.entity_id,
            "state": entity.state
        }
    }