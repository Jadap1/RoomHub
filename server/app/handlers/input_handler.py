from ..core.connection_manager import manager
from ..core.command_router import command_router


async def handle_input(message):

    print(
        "[INPUT EVENT]",
        message["payload"]
    )

    button = message["payload"].get("button")


    if button == "lights":

        command = {
            "version": "1.0",
            "type": "light.toggle",
            "source": message["source"],
            "target": "roomhub-core",
            "payload": {
                "entity_id": "test_light"
            }
        }

        return await command_router.execute(command)


    return {
        "version": "1.0",
        "type": "input.received",
        "payload": {
            "status": "ok"
        }
    }