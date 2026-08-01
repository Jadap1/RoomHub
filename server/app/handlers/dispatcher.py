from .endpoint_handler import handle_endpoint_register
from .heartbeat_handler import handle_heartbeat
from .input_handler import handle_input
from ..core.command_router import command_router


async def dispatch(message):

    message_type = message.get("type")


    if message_type == "endpoint.register":

        return await handle_endpoint_register(message)


    elif message_type == "endpoint.heartbeat":

        return await handle_heartbeat(message)

    elif message_type == "input.button":

        return await handle_input(message)


    return {
        "version": "1.0",
        "type": "error",
        "payload": {
            "message": f"Unknown message type: {message_type}"
        }
    }