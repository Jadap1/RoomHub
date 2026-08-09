from ..services.notification_service import notification_service


from ..services.notification_service import notification_service


async def handle_audio_status(message):
    payload = message.get("payload") or {}
    notification_service.update_status(
        payload.get("request_id"),
        message.get("source"),
        payload.get("status"),
    )
    notification_service.update_status(
        payload.get("request_id"),
        message.get("source"),
        payload.get("status"),
    )
    return {
        "version": "1.0",
        "type": "audio.status.ack",
        "target": message.get("source"),
        "payload": {
            "request_id": payload.get("request_id"),
            "status": payload.get("status"),
        },
    }
