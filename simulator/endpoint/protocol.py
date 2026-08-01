import json
import uuid
from datetime import datetime, timezone


PROTOCOL_VERSION = "1.0"


def create_message(
    message_type,
    source,
    target,
    payload
):

    return {
        "version": PROTOCOL_VERSION,
        "message_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": message_type,
        "source": source,
        "target": target,
        "payload": payload
    }


def encode_message(message):

    return json.dumps(message)