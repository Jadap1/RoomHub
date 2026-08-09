async def handle_audio_status(message):
    payload = message.get("payload") or {}
    return {
        "version": "1.0",
        "type": "audio.status.ack",
        "target": message.get("source"),
        "payload": {
            "request_id": payload.get("request_id"),
            "status": payload.get("status"),
        },
    }
