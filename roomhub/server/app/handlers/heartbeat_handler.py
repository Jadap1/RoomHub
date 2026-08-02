from datetime import datetime
from ..core.registry import registry
from ..core.state_manager import state_manager


async def handle_heartbeat(message):

    endpoint_id = message["source"]

    endpoint = registry.get(endpoint_id)

    if endpoint:

        endpoint.last_seen = datetime.now()

        endpoint.state = message.get(
            "payload",
            {}
        )

    return {
        "version": "1.0",
        "type": "endpoint.heartbeat_ack",
        "payload": {
            "time": datetime.now().isoformat()
        }
    }
    state_manager.update(
        message["source"],
        message["payload"]
    )