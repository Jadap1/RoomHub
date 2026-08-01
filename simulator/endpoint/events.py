from protocol import create_message


def create_event(event_type, source, payload):

    return create_message(
        message_type=event_type,
        source=source,
        target="roomhub-core",
        payload=payload
    )