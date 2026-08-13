from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from ..core.connection_manager import manager
from ..core.registry import registry


class EndpointControlRequest(BaseModel):
    screen_on: bool | None = None
    volume: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def require_control(self):
        if self.screen_on is None and self.volume is None:
            raise ValueError("screen_on or volume is required")
        return self


class EndpointControlService:
    async def apply(self, endpoint_id: str, request: EndpointControlRequest) -> dict:
        endpoint = registry.get(endpoint_id)
        if endpoint is None:
            return {"status": "not_found", "endpoint_id": endpoint_id}
        if not endpoint.connected or manager.get(endpoint_id) is None:
            return {"status": "unavailable", "endpoint_id": endpoint_id}
        request_id = uuid4().hex
        controls = request.model_dump(exclude_none=True)
        sent = await manager.send(endpoint_id, {
            "version": "1.0",
            "type": "endpoint.control",
            "source": "roomhub-core",
            "target": endpoint_id,
            "payload": {"request_id": request_id, **controls},
        })
        return {
            "status": "sent" if sent else "unavailable",
            "endpoint_id": endpoint_id,
            "request_id": request_id,
            "controls": controls,
        }

    def update(self, endpoint_id: str | None, payload: dict) -> dict:
        endpoint = registry.get(endpoint_id) if endpoint_id else None
        if endpoint is None:
            return {"status": "not_found"}
        controls = endpoint.state.setdefault("controls", {})
        if isinstance(payload.get("screen_on"), bool):
            controls["screen_on"] = payload["screen_on"]
        volume = payload.get("volume")
        if isinstance(volume, int) and not isinstance(volume, bool) and 0 <= volume <= 100:
            controls["volume"] = volume
        return {
            "version": "1.0",
            "type": "endpoint.control.ack",
            "payload": {
                "request_id": payload.get("request_id"),
                "status": payload.get("status", "applied"),
                **controls,
            },
        }


endpoint_control_service = EndpointControlService()
