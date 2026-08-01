from ..core.connection_manager import manager


async def handle_input(message):

    button = message["payload"].get("button")

    endpoint_id = message["source"]


    print(
        "[INPUT EVENT]",
        message["payload"]
    )


    if button == "lights":

        await manager.send(
            endpoint_id,
            {
                "version": "1.0",
                "type": "display.show",
                "source": "roomhub-core",
                "target": endpoint_id,
                "payload": {
                    "screen": "lights"
                }
            }
        )


    return {
        "version": "1.0",
        "type": "input.received",
        "payload": {
            "status": "ok"
        }
    }