from uuid import uuid4

from pydantic import BaseModel, field_validator

from ..core.connection_manager import manager


class AudioPlayRequest(BaseModel):
    url: str
    mime_type: str = "audio/mpeg"
    priority: str = "notification"
    request_id: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("audio URL must use HTTP or HTTPS")
        return value

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, value: str) -> str:
        if value != "audio/mpeg":
            raise ValueError("only audio/mpeg is currently supported")
        return value

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        allowed = {
            "emergency", "intercom", "voice_assistant",
            "media", "notification",
        }
        if value not in allowed:
            raise ValueError("unsupported audio priority")
        return value


class AudioCommandService:
    async def play(
        self,
        endpoint_id: str,
        request: AudioPlayRequest,
    ) -> dict:
        if manager.get(endpoint_id) is None:
            return {"status": "unavailable", "target": endpoint_id}
        request_id = request.request_id or uuid4().hex
        await manager.send(endpoint_id, {
            "version": "1.0",
            "type": "audio.play",
            "source": "roomhub-core",
            "target": endpoint_id,
            "payload": {
                "request_id": request_id,
                "url": request.url,
                "mime_type": request.mime_type,
                "priority": request.priority,
            },
        })
        return {
            "status": "sent",
            "target": endpoint_id,
            "request_id": request_id,
        }

    async def stop(self, endpoint_id: str, request_id: str) -> dict:
        if manager.get(endpoint_id) is None:
            return {"status": "unavailable", "target": endpoint_id}
        await manager.send(endpoint_id, {
            "version": "1.0",
            "type": "audio.stop",
            "source": "roomhub-core",
            "target": endpoint_id,
            "payload": {"request_id": request_id},
        })
        return {
            "status": "sent",
            "target": endpoint_id,
            "request_id": request_id,
        }


audio_command_service = AudioCommandService()
