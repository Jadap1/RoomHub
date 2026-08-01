import uuid
import json


def create_message(message_type, source, target, payload):

    return {
        "version": "1.0",
        "id": str(uuid.uuid4()),
        "type": message_type,
        "source": source,
        "target": target,
        "payload": payload
    }


def encode_message(message):

    return json.dumps(message)