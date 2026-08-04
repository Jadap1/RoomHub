import re
from collections.abc import Awaitable, Callable
from typing import Any

from ..core.area_registry import area_registry
from ..core.entity_registry import entity_registry
from ..core.event_bus import PublishResult, event_bus
from ..core.registry import registry
from ..events.entity_events import EntityCommandEvent
from ..models.intent import (
    IntentResolutionError,
    ResolvedEntityIntent,
)


PublishEvent = Callable[[Any], Awaitable[PublishResult]]

_COMMAND_PATTERNS = (
    (
        re.compile(
            r"^(?:turn|switch)\s+(?P<state>on|off)\s+"
            r"(?P<target>.+)$",
            re.IGNORECASE,
        ),
        None,
    ),
    (
        re.compile(
            r"^toggle\s+(?P<target>.+)$",
            re.IGNORECASE,
        ),
        "toggle",
    ),
)

_SUPPORTED_DOMAINS = {
    "fan",
    "input_boolean",
    "light",
    "switch",
}


def _normalise(value: str) -> str:
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    value = value.casefold().strip()
    value = re.sub(r"[._-]+", " ", value)
    value = re.sub(r"[^\w\s]+", " ", value)
    return " ".join(value.split())


class VoiceIntentService:
    def __init__(
        self,
        entities=entity_registry,
        areas=area_registry,
        endpoints=registry,
        publish: PublishEvent = event_bus.publish,
    ) -> None:
        self._entities = entities
        self._areas = areas
        self._endpoints = endpoints
        self._publish = publish

    def resolve(
        self,
        transcript: str,
        area_id: str | None = None,
    ) -> ResolvedEntityIntent:
        text = transcript.strip()
        text = re.sub(
            r"^(?:please\s+)+",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\s+please[.!?]*$",
            "",
            text,
            flags=re.IGNORECASE,
        )

        command = None
        target = None
        for pattern, fixed_command in _COMMAND_PATTERNS:
            match = pattern.match(text)
            if match is None:
                continue
            target = match.group("target").strip()
            state = match.groupdict().get("state")
            command = fixed_command or f"turn_{state}"
            break

        if command is None or target is None:
            raise IntentResolutionError(
                "unsupported_intent",
                "Only turn on, turn off, and toggle commands are supported.",
            )

        target_key = _normalise(
            re.sub(
                r"^the\s+",
                "",
                target,
                flags=re.IGNORECASE,
            )
        )
        candidates = []

        for entity in self._entities.entities.values():
            domain = entity.entity_id.split(".", 1)[0]
            if domain not in _SUPPORTED_DOMAINS:
                continue
            if area_id is not None and entity.area_id != area_id:
                continue

            names = {
                _normalise(entity.entity_id),
                _normalise(entity.name),
            }
            if target_key in names:
                candidates.append(entity)

        if not candidates:
            raise IntentResolutionError(
                "entity_not_found",
                f"No controllable entity matches '{target}'.",
            )

        if len(candidates) > 1:
            candidate_ids = sorted(
                entity.entity_id for entity in candidates
            )
            raise IntentResolutionError(
                "ambiguous_entity",
                f"More than one entity matches '{target}'.",
                candidate_ids,
            )

        return ResolvedEntityIntent(
            entity_id=candidates[0].entity_id,
            command=command,
            transcript=transcript,
            area_id=area_id,
        )

    def endpoint_area_id(
        self,
        endpoint_id: str | None,
    ) -> str | None:
        if not endpoint_id:
            return None
        endpoint = self._endpoints.get(endpoint_id)
        if endpoint is None:
            return None
        room_key = _normalise(endpoint.room)
        matches = [
            area.area_id
            for area in self._areas.areas.values()
            if room_key in {
                _normalise(area.area_id),
                _normalise(area.name),
            }
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    async def handle_transcript(
        self,
        transcript: str,
        endpoint_id: str | None = None,
        area_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_area_id = (
            area_id or self.endpoint_area_id(endpoint_id)
        )

        try:
            intent = self.resolve(
                transcript,
                resolved_area_id,
            )
        except IntentResolutionError as error:
            payload: dict[str, Any] = {
                "status": "rejected",
                "reason": error.code,
                "message": str(error),
            }
            if error.candidates:
                payload["candidates"] = error.candidates
            return {
                "version": "1.0",
                "type": "voice.intent.rejected",
                "payload": payload,
            }

        result = await self._publish(
            EntityCommandEvent(
                entity_id=intent.entity_id,
                command=intent.command,
            )
        )

        if (
            result.successful_handlers == 0
            or result.failed_handlers > 0
        ):
            return {
                "version": "1.0",
                "type": "voice.intent.failed",
                "payload": {
                    "status": "failed",
                    "reason": "command_delivery_failed",
                    "entity_id": intent.entity_id,
                    "command": intent.command,
                },
            }

        return {
            "version": "1.0",
            "type": "voice.intent.accepted",
            "payload": {
                "status": "accepted",
                "entity_id": intent.entity_id,
                "command": intent.command,
                "area_id": intent.area_id,
            },
        }


voice_intent_service = VoiceIntentService()
