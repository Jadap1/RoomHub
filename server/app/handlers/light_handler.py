async def handle_light_toggle(message):

    print(
        "[LIGHT COMMAND]",
        message["payload"]
    )

    return {
        "version": "1.0",
        "type": "light.toggle.received",
        "payload": {
            "status": "ok"
        }
    }