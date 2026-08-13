from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from ..core.connection_manager import manager
from ..core.entity_registry import entity_registry
from ..core.event_bus import event_bus
from ..core.registry import registry
from ..events.entity_events import EntityCommandEvent
from ..integrations.homeassistant.tts_pipeline import HomeAssistantTextToSpeechClient
from .audio_command_service import AudioPlayRequest, audio_command_service


class NotificationAction(BaseModel):
    label: str = Field(min_length=1, max_length=30)
    entity_id: str

    @field_validator("label")
    @classmethod
    def trim_label(cls, value: str) -> str:
        return value.strip()

    @field_validator("entity_id")
    @classmethod
    def validate_entity_id(cls, value: str) -> str:
        if not value.startswith(("script.", "scene.")):
            raise ValueError("notification actions must target a script or scene")
        return value


class NotificationRequest(BaseModel):
    text: str
    title: str = "RoomHub"
    endpoint_id: str | None = None
    area_id: str | None = None
    priority: str = "notification"
    display: bool = True
    speak: bool = True
    timeout_seconds: int = Field(default=0, ge=0, le=3600)
    presentation: str = "replace"
    actions: list[NotificationAction] = Field(default_factory=list, max_length=2)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("notification text must not be empty")
        if len(value) > 1000:
            raise ValueError("notification text must be at most 1000 characters")
        return value

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("notification title must not be empty")
        if len(value) > 80:
            raise ValueError("notification title must be at most 80 characters")
        return value

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        if value not in {"notification", "emergency"}:
            raise ValueError("notification priority must be notification or emergency")
        return value

    @field_validator("presentation")
    @classmethod
    def validate_presentation(cls, value: str) -> str:
        if value not in {"replace", "queue"}:
            raise ValueError("notification presentation must be replace or queue")
        return value

    @model_validator(mode="after")
    def validate_target(self):
        if (self.endpoint_id is None) == (self.area_id is None):
            raise ValueError("provide exactly one of endpoint_id or area_id")
        if not self.display and not self.speak:
            raise ValueError("enable at least one notification channel")
        return self


class NotificationService:
    def __init__(self, tts_factory=HomeAssistantTextToSpeechClient) -> None:
        self._tts_factory = tts_factory
        self.deliveries: dict[str, dict] = {}

    def _targets(self, request: NotificationRequest) -> list[str]:
        endpoints = registry.endpoints.values()
        return [
            endpoint.device_id
            for endpoint in endpoints
            if endpoint.connected
            and (
                (request.display and "display" in endpoint.capabilities)
                or (request.speak and "speaker" in endpoint.capabilities)
            )
            and (
                endpoint.device_id == request.endpoint_id
                if request.endpoint_id is not None
                else endpoint.area_id == request.area_id
            )
        ]

    async def notify(self, request: NotificationRequest) -> dict:
        targets = self._targets(request)
        if not targets:
            return {
                "status": "unavailable",
                "endpoint_id": request.endpoint_id,
                "area_id": request.area_id,
                "targets": [],
            }

        delivery_id = uuid4().hex
        delivery = {
            "delivery_id": delivery_id,
            "status": "sent",
            "text": request.text,
            "title": request.title,
            "priority": request.priority,
            "timeout_seconds": request.timeout_seconds,
            "presentation": request.presentation,
            "actions": [action.model_dump() for action in request.actions],
            "endpoint_id": request.endpoint_id,
            "area_id": request.area_id,
            "created_at": datetime.now(UTC).isoformat(),
            "targets": {target: "sent" for target in targets},
            "channels": {},
        }
        for target in targets:
            endpoint = registry.get(target)
            delivery["channels"][target] = {
                channel: "sent"
                for channel, capability in (
                    ("visual", "display"), ("audio", "speaker")
                )
                if endpoint is not None and capability in endpoint.capabilities
                and ((channel == "visual" and request.display)
                     or (channel == "audio" and request.speak))
            }
        self.deliveries[delivery_id] = delivery
        for target in targets:
            endpoint = registry.get(target)
            if (request.display and endpoint is not None
                and "display" in endpoint.capabilities):
                await manager.send(target, {
                    "version": "1.0",
                    "type": "notification.show",
                    "source": "roomhub-core",
                    "target": target,
                    "payload": {
                        "delivery_id": delivery_id,
                        "title": request.title,
                        "text": request.text,
                        "priority": request.priority,
                        "timeout_seconds": request.timeout_seconds,
                        "presentation": request.presentation,
                        "actions": [action.model_dump() for action in request.actions],
                    },
                })
        speaker_targets = [
            target for target in targets
            if request.speak and "speaker" in (
                registry.get(target).capabilities if registry.get(target) else []
            )
        ]
        if speaker_targets:
            speech = await self._tts_factory().synthesize(request.text)
            for target in speaker_targets:
                await audio_command_service.play(target, AudioPlayRequest(
                    request_id=delivery_id,
                    url=speech.url,
                    mime_type=speech.mime_type,
                    priority=request.priority,
                ))
        return deepcopy(delivery)

    async def activate_action(
        self, delivery_id: str | None, endpoint_id: str | None,
        entity_id: str | None,
    ) -> dict:
        delivery = self.deliveries.get(delivery_id or "")
        allowed = {
            action["entity_id"] for action in delivery.get("actions", [])
        } if delivery else set()
        entity = entity_registry.get(entity_id) if isinstance(entity_id, str) else None
        if (delivery is None or endpoint_id not in delivery["targets"]
            or entity_id not in allowed or entity is None
            or entity.entity_type not in {"script", "scene"}):
            return {"status": "rejected", "reason": "invalid_notification_action"}
        await event_bus.publish(EntityCommandEvent(
            entity_id=entity_id, command="turn_on", data={}
        ))
        delivery["action"] = {
            "endpoint_id": endpoint_id,
            "entity_id": entity_id,
            "activated_at": datetime.now(UTC).isoformat(),
        }
        return {"status": "activated", "entity_id": entity_id}

    def update_status(
        self,
        delivery_id: str | None,
        endpoint_id: str | None,
        status: str | None,
        channel: str = "audio",
    ) -> None:
        if not delivery_id or not endpoint_id or not status:
            return
        delivery = self.deliveries.get(delivery_id)
        if (delivery is None or endpoint_id not in delivery["targets"]
            or channel not in delivery["channels"].get(endpoint_id, {})):
            return
        delivery["channels"][endpoint_id][channel] = status
        self._summarize(delivery)

    @staticmethod
    def _summarize(delivery: dict) -> None:
        terminal = {"completed", "dismissed", "expired", "replaced", "interrupted", "failed", "stopped", "not_found"}
        errors = {"interrupted", "failed", "stopped", "not_found"}
        for endpoint_id, channels in delivery["channels"].items():
            statuses = set(channels.values())
            if statuses <= terminal:
                if statuses & errors:
                    summary = "finished_with_errors"
                elif statuses & {"dismissed", "expired", "replaced"}:
                    summary = next(
                        value for value in ("dismissed", "expired", "replaced")
                        if value in statuses
                    )
                else:
                    summary = "completed"
            elif "playing" in statuses:
                summary = "playing"
            elif "accepted" in statuses:
                summary = "accepted"
            else:
                summary = "sent"
            delivery["targets"][endpoint_id] = summary

        statuses = set(delivery["targets"].values())
        successful = {"completed", "dismissed", "expired", "replaced"}
        if statuses <= successful | {"finished_with_errors"}:
            if "finished_with_errors" in statuses:
                delivery["status"] = "finished_with_errors"
            elif statuses & {"dismissed", "expired", "replaced"}:
                delivery["status"] = next(
                    value for value in ("dismissed", "expired", "replaced")
                    if value in statuses
                )
            else:
                delivery["status"] = "completed"
        elif "playing" in statuses:
            delivery["status"] = "playing"
        elif "accepted" in statuses:
            delivery["status"] = "accepted"
        else:
            delivery["status"] = "sent"

    def get(self, delivery_id: str) -> dict | None:
        delivery = self.deliveries.get(delivery_id)
        return None if delivery is None else deepcopy(delivery)


notification_service = NotificationService()
