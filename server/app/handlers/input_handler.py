async def handle_input(message):

    print(
        "[INPUT EVENT]",
        message["payload"]
    )

    return {
        "version": "1.0",
        "type": "input.received",
        "payload": {
            "status": "ok"
        }
    }