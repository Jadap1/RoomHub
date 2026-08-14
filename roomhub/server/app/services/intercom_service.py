from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.connection_manager import manager
from ..core.registry import registry


def _message(message_type: str, **payload: Any) -> dict[str, Any]:
    return {"version": "1.0", "type": message_type, "payload": payload}


@dataclass(frozen=True)
class IntercomSession:
    source_id: str
    target_id: str


class IntercomService:
    maximum_frame_bytes = 8192

    def __init__(self) -> None:
        self._by_source: dict[str, IntercomSession] = {}
        self._endpoint_sessions: dict[str, IntercomSession] = {}

    def targets(self, endpoint_id: str) -> list[dict[str, Any]]:
        targets = []
        for candidate in registry.endpoints.values():
            if (
                candidate.device_id == endpoint_id
                or not candidate.connected
                or manager.get(candidate.device_id) is None
                or "speaker" not in candidate.capabilities
            ):
                continue
            targets.append({
                "endpoint_id": candidate.device_id,
                "name": candidate.device_name,
                "room": candidate.room,
                "area_id": candidate.area_id,
            })
        return sorted(
            targets,
            key=lambda item: (item["room"].casefold(), item["name"].casefold()),
        )

    async def broadcast_targets(self, exclude_endpoint_id: str | None = None) -> None:
        for endpoint_id in tuple(manager.connections):
            if endpoint_id == exclude_endpoint_id:
                continue
            await manager.send(endpoint_id, _message(
                "intercom.targets",
                targets=self.targets(endpoint_id),
            ))

    async def start(
        self,
        source_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        target_id = payload.get("target_endpoint_id")
        source = registry.get(source_id)
        target = registry.get(target_id) if isinstance(target_id, str) else None
        if target_id == source_id:
            return self._rejected("source_is_target")
        if (
            source is None
            or "microphone" not in source.capabilities
            or source.state.get("controls", {}).get("microphone_muted") is True
        ):
            return self._rejected("source_microphone_unavailable")
        if (
            target is None
            or not target.connected
            or "speaker" not in target.capabilities
            or manager.get(target.device_id) is None
        ):
            return self._rejected("target_unavailable")
        if source_id in self._endpoint_sessions or target.device_id in self._endpoint_sessions:
            return self._rejected("endpoint_busy")
        if (
            payload.get("sample_rate") != 16000
            or payload.get("channels") != 1
            or payload.get("format") != "pcm_s16le"
        ):
            return self._rejected("unsupported_audio_format")

        session = IntercomSession(source_id, target.device_id)
        self._by_source[source_id] = session
        self._endpoint_sessions[source_id] = session
        self._endpoint_sessions[target.device_id] = session
        delivered = await manager.send(target.device_id, _message(
            "intercom.incoming",
            source_endpoint_id=source_id,
            source_name=source.device_name,
            source_room=source.room,
            sample_rate=16000,
            channels=1,
            format="pcm_s16le",
        ))
        if not delivered:
            self._release(session)
            return self._rejected("target_unavailable")
        return _message(
            "intercom.ready",
            target_endpoint_id=target.device_id,
            target_name=target.device_name,
            target_room=target.room,
        )

    async def send_audio(self, source_id: str, audio: bytes) -> dict | None:
        session = self._by_source.get(source_id)
        if session is None:
            return self._rejected("no_active_session")
        if not audio or len(audio) > self.maximum_frame_bytes or len(audio) % 2:
            await self.stop(source_id, "invalid_audio_frame")
            return self._rejected("invalid_audio_frame")
        if not await manager.send_bytes(session.target_id, audio):
            await self.stop(source_id, "target_disconnected")
            return self._rejected("target_unavailable")
        return None

    async def stop(self, source_id: str, reason: str = "completed") -> dict[str, Any]:
        session = self._by_source.get(source_id)
        if session is None:
            return self._rejected("no_active_session")
        self._release(session)
        await manager.send(session.target_id, _message(
            "intercom.ended",
            source_endpoint_id=source_id,
            reason=reason,
        ))
        return _message(
            "intercom.ended",
            target_endpoint_id=session.target_id,
            reason=reason,
        )

    async def close_endpoint(self, endpoint_id: str) -> None:
        session = self._endpoint_sessions.get(endpoint_id)
        if session is None:
            return
        self._release(session)
        peer_id = (
            session.target_id if endpoint_id == session.source_id
            else session.source_id
        )
        await manager.send(peer_id, _message(
            "intercom.ended",
            reason="peer_disconnected",
        ))

    def is_transmitting(self, endpoint_id: str) -> bool:
        return endpoint_id in self._by_source

    def reset(self) -> None:
        self._by_source.clear()
        self._endpoint_sessions.clear()

    def _release(self, session: IntercomSession) -> None:
        self._by_source.pop(session.source_id, None)
        self._endpoint_sessions.pop(session.source_id, None)
        self._endpoint_sessions.pop(session.target_id, None)

    @staticmethod
    def _rejected(reason: str) -> dict[str, Any]:
        return _message("intercom.rejected", status="rejected", reason=reason)


intercom_service = IntercomService()
