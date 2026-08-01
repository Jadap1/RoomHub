from .connection_manager import manager
from datetime import datetime
import json


async def send_command(
    device_id,
    message_type,
    payload
):

    websocket = manager.get(device_id)


    if websocket is None:

        print(
            f"[COMMAND] Endpoint not connected: {device_id}"
        )

        return False


    message = {
        "version": "1.0",
        "type": message_type,
        "source": "roomhub-core",
        "target": device_id,
        "payload": payload
    }


    await websocket.send(
        json.dumps(message)
    )


    print(
        f"[COMMAND] Sent {message_type} to {device_id}"
    )


    return True