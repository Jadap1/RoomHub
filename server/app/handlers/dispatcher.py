from .endpoint_handler import handle_endpoint_register


async def dispatch(message):

    message_type = message.get("type")


    if message_type == "endpoint.register":

        return await handle_endpoint_register(message)


    return {
        "version": "1.0",
        "type": "error",
        "payload": {
            "message": f"Unknown message type: {message_type}"
        }
    }