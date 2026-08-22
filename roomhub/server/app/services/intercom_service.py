from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from ..core.connection_manager import manager
from ..core.registry import registry


def _message(message_type: str, **payload: Any) -> dict[str, Any]:
    return {"version": "1.0", "type": message_type, "payload": payload}


@dataclass
class IntercomSession:
    call_id: str
    source_id: str
    target_id: str
    state: str = "ringing"
    timeout_task: asyncio.Task | None = None

    def peer(self, endpoint_id: str) -> str | None:
        if endpoint_id == self.source_id:
            return self.target_id
        if endpoint_id == self.target_id:
            return self.source_id
        return None


class IntercomService:
    maximum_frame_bytes = 8192

    def __init__(self, ringing_timeout_seconds: float = 30.0) -> None:
        self.ringing_timeout_seconds = ringing_timeout_seconds
        self._endpoint_sessions: dict[str, IntercomSession] = {}

    def targets(self, endpoint_id: str) -> list[dict[str, Any]]:
        targets = []
        for candidate in registry.endpoints.values():
            if (
                candidate.device_id == endpoint_id
                or not candidate.connected
                or manager.get(candidate.device_id) is None
                or "speaker" not in candidate.capabilities
                or "microphone" not in candidate.capabilities
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
            or "speaker" not in source.capabilities
            or source.state.get("controls", {}).get("microphone_muted") is True
        ):
            return self._rejected("source_audio_unavailable")
        if (
            target is None
            or not target.connected
            or "speaker" not in target.capabilities
            or "microphone" not in target.capabilities
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

        session = IntercomSession(uuid4().hex, source_id, target.device_id)
        self._endpoint_sessions[source_id] = session
        self._endpoint_sessions[target.device_id] = session
        delivered = await manager.send(target.device_id, _message(
            "intercom.incoming",
            call_id=session.call_id,
            source_endpoint_id=source_id,
            source_name=source.device_name,
            source_room=source.room,
            sample_rate=16000,
            channels=1,
            format="pcm_s16le",
            timeout_seconds=int(self.ringing_timeout_seconds),
        ))
        if not delivered:
            self._release(session)
            return self._rejected("target_unavailable")
        session.timeout_task = asyncio.create_task(self._expire_ringing(session))
        return _message(
            "intercom.ringing",
            call_id=session.call_id,
            target_endpoint_id=target.device_id,
            target_name=target.device_name,
            target_room=target.room,
            timeout_seconds=int(self.ringing_timeout_seconds),
        )

    async def target_status(
        self,
        target_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        session = self._endpoint_sessions.get(target_id)
        if (
            session is None
            or session.target_id != target_id
            or session.state != "ringing"
            or payload.get("call_id") != session.call_id
        ):
            return self._rejected("no_incoming_call")
        status = payload.get("status")
        if status == "accepted":
            session.state = "active"
            self._cancel_timeout(session)
            target = registry.get(session.target_id)
            active = _message(
                "intercom.active",
                call_id=session.call_id,
                peer_endpoint_id=session.target_id,
                peer_name=target.device_name if target else session.target_id,
                peer_room=target.room if target else "Unknown room",
            )
            if not await manager.send(session.source_id, active):
                self._release(session)
                return self._rejected("source_unavailable")
            source = registry.get(session.source_id)
            return _message(
                "intercom.active",
                call_id=session.call_id,
                peer_endpoint_id=session.source_id,
                peer_name=source.device_name if source else session.source_id,
                peer_room=source.room if source else "Unknown room",
            )
        if status == "declined":
            self._release(session)
            await manager.send(
                session.source_id,
                self._rejected("declined", call_id=session.call_id),
            )
            return _message(
                "intercom.ended", call_id=session.call_id, reason="declined"
            )
        return self._rejected("invalid_call_status", call_id=session.call_id)

    async def send_audio(self, endpoint_id: str, audio: bytes) -> dict | None:
        session = self._endpoint_sessions.get(endpoint_id)
        if session is None or session.state != "active":
            return self._rejected("no_active_call")
        if not audio or len(audio) > self.maximum_frame_bytes or len(audio) % 2:
            await self.stop(endpoint_id, {"call_id": session.call_id}, "invalid_audio_frame")
            return self._rejected("invalid_audio_frame", call_id=session.call_id)
        peer_id = session.peer(endpoint_id)
        if peer_id is None or not await manager.send_bytes(peer_id, audio):
            await self.stop(endpoint_id, {"call_id": session.call_id}, "peer_disconnected")
            return self._rejected("peer_unavailable", call_id=session.call_id)
        return None

    async def stop(
        self,
        endpoint_id: str,
        payload: dict[str, Any] | str | None = None,
        reason: str = "completed",
    ) -> dict[str, Any]:
        session = self._endpoint_sessions.get(endpoint_id)
        if session is None:
            return self._rejected("no_active_call")
        # Keep compatibility with endpoints using the original two-argument
        # stop call while newer callers include the stable call ID.
        if isinstance(payload, str):
            reason = payload
            payload = None
        call_id = (payload or {}).get("call_id")
        if call_id is not None and call_id != session.call_id:
            return self._rejected("call_id_mismatch")
        peer_id = session.peer(endpoint_id)
        self._release(session)
        ended = _message("intercom.ended", call_id=session.call_id, reason=reason)
        if peer_id is not None:
            await manager.send(peer_id, ended)
        return ended

    async def close_endpoint(self, endpoint_id: str) -> None:
        session = self._endpoint_sessions.get(endpoint_id)
        if session is None:
            return
        peer_id = session.peer(endpoint_id)
        self._release(session)
        if peer_id is not None:
            await manager.send(peer_id, _message(
                "intercom.ended",
                call_id=session.call_id,
                reason="peer_disconnected",
            ))

    def has_session(self, endpoint_id: str) -> bool:
        return endpoint_id in self._endpoint_sessions

    def is_transmitting(self, endpoint_id: str) -> bool:
        session = self._endpoint_sessions.get(endpoint_id)
        return session is not None and session.state == "active"

    def reset(self) -> None:
        unique_sessions = {id(item): item for item in self._endpoint_sessions.values()}
        for session in unique_sessions.values():
            self._cancel_timeout(session)
        self._endpoint_sessions.clear()

    async def _expire_ringing(self, session: IntercomSession) -> None:
        try:
            await asyncio.sleep(self.ringing_timeout_seconds)
        except asyncio.CancelledError:
            return
        if (
            self._endpoint_sessions.get(session.source_id) is not session
            or session.state != "ringing"
        ):
            return
        self._release(session)
        await manager.send(
            session.target_id,
            _message("intercom.ended", call_id=session.call_id, reason="missed"),
        )
        await manager.send(
            session.source_id,
            self._rejected("no_answer", call_id=session.call_id),
        )

    def _release(self, session: IntercomSession) -> None:
        self._cancel_timeout(session)
        self._endpoint_sessions.pop(session.source_id, None)
        self._endpoint_sessions.pop(session.target_id, None)

    @staticmethod
    def _cancel_timeout(session: IntercomSession) -> None:
        task = session.timeout_task
        session.timeout_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    @staticmethod
    def _rejected(reason: str, call_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": "rejected", "reason": reason}
        if call_id is not None:
            payload["call_id"] = call_id
        return _message("intercom.rejected", **payload)


intercom_service = IntercomService()
