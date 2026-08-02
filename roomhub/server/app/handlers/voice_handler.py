from ..services.voice_intent_service import (
    voice_intent_service,
)


async def handle_voice_transcript(message):
    payload = message.get("payload") or {}
    transcript = payload.get("text")

    if not isinstance(transcript, str) or not transcript.strip():
        return {
            "version": "1.0",
            "type": "voice.intent.rejected",
            "payload": {
                "status": "rejected",
                "reason": "invalid_transcript",
                "message": "A non-empty transcript is required.",
            },
        }

    area_id = payload.get("area_id")
    if area_id is not None and not isinstance(area_id, str):
        return {
            "version": "1.0",
            "type": "voice.intent.rejected",
            "payload": {
                "status": "rejected",
                "reason": "invalid_area",
                "message": "area_id must be a string when supplied.",
            },
        }

    return await voice_intent_service.handle_transcript(
        transcript=transcript,
        endpoint_id=message.get("source"),
        area_id=area_id,
    )
