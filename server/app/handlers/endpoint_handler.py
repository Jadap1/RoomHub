from ..services.endpoint_service import register_endpoint


async def handle_endpoint_register(message):

    endpoint = register_endpoint(
        message["payload"]
    )

    return {
        "version": "1.0",
        "type": "endpoint.registered",
        "payload": {
            "device_id": endpoint.device_id,
            "room": endpoint.room
        }
    }