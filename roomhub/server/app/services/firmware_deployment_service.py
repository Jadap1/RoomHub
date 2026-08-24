import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from ..core.connection_manager import manager
from ..core.registry import registry
from .firmware_audit import firmware_audit
from .firmware_service import FirmwareManifest


class FirmwareDeploymentService:
    def __init__(self, acknowledgement_timeout: float = 8.0):
        self.acknowledgement_timeout = acknowledgement_timeout
        self.deployments: dict[str, dict] = {}
        self._timeouts: dict[str, asyncio.Task] = {}

    def get(self, endpoint_id: str) -> dict | None:
        return self.deployments.get(endpoint_id)

    async def deploy(self, endpoint_id: str, manifest: FirmwareManifest) -> dict:
        endpoint = registry.get(endpoint_id)
        if endpoint is None or not endpoint.connected or manager.get(endpoint_id) is None:
            raise ConnectionError("endpoint not connected")
        request_id = uuid4().hex
        state = {
            "request_id": request_id,
            "endpoint_id": endpoint_id,
            "version": manifest.version,
            "status": "sent",
            "progress": 0,
            "reason": None,
            "attempts": self.deployments.get(endpoint_id, {}).get("attempts", 0) + 1,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self.deployments[endpoint_id] = state
        sent = await manager.send(endpoint_id, {
            "version": "1.0",
            "type": "firmware.update",
            "source": "roomhub-core",
            "target": endpoint_id,
            "payload": {
                "request_id": request_id,
                "version": manifest.version,
                "size": manifest.size,
                "sha256": manifest.sha256,
                "path": manifest.path,
            },
        })
        if not sent:
            state.update(status="failed", reason="socket_send_failed")
            raise ConnectionError("firmware command could not be sent")
        self._cancel_timeout(endpoint_id)
        self._timeouts[endpoint_id] = asyncio.create_task(
            self._mark_unacknowledged(endpoint_id, request_id)
        )
        firmware_audit.record("deployed", **state)
        return state.copy()

    async def _mark_unacknowledged(self, endpoint_id: str, request_id: str) -> None:
        await asyncio.sleep(self.acknowledgement_timeout)
        state = self.deployments.get(endpoint_id)
        if state and state["request_id"] == request_id and state["status"] == "sent":
            state.update(
                status="unacknowledged",
                reason="endpoint_did_not_acknowledge",
                updated_at=datetime.now(UTC).isoformat(),
            )
            firmware_audit.record("unacknowledged", **state)

    def update(self, endpoint_id: str, payload: dict) -> dict:
        state = self.deployments.get(endpoint_id)
        if state is None or payload.get("request_id") != state["request_id"]:
            return {"status": "ignored", "reason": "unknown_request"}
        status = payload.get("status")
        allowed = {"accepted", "downloading", "installing", "restarting", "failed"}
        if status not in allowed:
            return {"status": "ignored", "reason": "invalid_status"}
        progress = payload.get("progress", state["progress"])
        state.update(
            status=status,
            progress=max(0, min(100, int(progress))) if isinstance(progress, (int, float)) else state["progress"],
            reason=payload.get("reason"),
            updated_at=datetime.now(UTC).isoformat(),
        )
        if status != "sent":
            self._cancel_timeout(endpoint_id)
        firmware_audit.record("status", **state)
        return state.copy()

    def mark_running(self, endpoint_id: str, version: str | None) -> None:
        state = self.deployments.get(endpoint_id)
        if state and version == state["version"]:
            state.update(
                status="completed", progress=100, reason=None,
                updated_at=datetime.now(UTC).isoformat(),
            )
            self._cancel_timeout(endpoint_id)

    async def retry_after_registration(
        self, endpoint_id: str, running_version: str | None, manifest: FirmwareManifest | None
    ) -> dict | None:
        state = self.deployments.get(endpoint_id)
        if (
            state is None or manifest is None or running_version == state["version"]
            or manifest.version != state["version"]
            or state["status"] not in {"unacknowledged", "failed"}
            or state["attempts"] >= 3
        ):
            return None
        await asyncio.sleep(0.25)
        return await self.deploy(endpoint_id, manifest)

    def _cancel_timeout(self, endpoint_id: str) -> None:
        task = self._timeouts.pop(endpoint_id, None)
        if task and task is not asyncio.current_task():
            task.cancel()


firmware_deployment_service = FirmwareDeploymentService()
