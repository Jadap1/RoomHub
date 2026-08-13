import asyncio
import secrets
from dataclasses import dataclass, field
from uuid import uuid4

from ..core.connection_manager import manager
from ..core.registry import registry


class CameraSnapshotError(Exception):
    pass


class CameraSnapshotUnavailable(CameraSnapshotError):
    pass


class CameraSnapshotTimeout(CameraSnapshotError):
    pass


@dataclass
class PendingSnapshot:
    endpoint_id: str
    token: str
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    image: bytes | None = None


class CameraSnapshotService:
    max_image_size = 1_500_000

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self._pending: dict[str, PendingSnapshot] = {}
        self._endpoint_locks: dict[str, asyncio.Lock] = {}

    async def capture(self, endpoint_id: str) -> bytes:
        endpoint = registry.get(endpoint_id)
        if endpoint is None:
            raise KeyError(endpoint_id)
        if (
            not endpoint.connected
            or manager.get(endpoint_id) is None
            or "camera" not in endpoint.capabilities
        ):
            raise CameraSnapshotUnavailable("endpoint camera unavailable")

        lock = self._endpoint_locks.setdefault(endpoint_id, asyncio.Lock())
        async with lock:
            request_id = uuid4().hex
            pending = PendingSnapshot(endpoint_id, secrets.token_urlsafe(32))
            self._pending[request_id] = pending
            try:
                sent = await manager.send(endpoint_id, {
                    "version": "1.0",
                    "type": "camera.capture",
                    "source": "roomhub-core",
                    "target": endpoint_id,
                    "payload": {
                        "request_id": request_id,
                        "upload_path": (
                            f"/api/endpoints/{endpoint_id}/camera/upload/{request_id}"
                        ),
                        "upload_token": pending.token,
                    },
                })
                if not sent:
                    raise CameraSnapshotUnavailable("capture command was not delivered")
                try:
                    await asyncio.wait_for(pending.ready.wait(), self.timeout)
                except TimeoutError as error:
                    raise CameraSnapshotTimeout("camera capture timed out") from error
                if pending.image is None:
                    raise CameraSnapshotUnavailable("camera capture failed")
                return pending.image
            finally:
                self._pending.pop(request_id, None)

    def upload(
        self, endpoint_id: str, request_id: str, token: str | None, image: bytes
    ) -> None:
        pending = self._pending.get(request_id)
        if pending is None or pending.endpoint_id != endpoint_id:
            raise KeyError(request_id)
        if token is None or not secrets.compare_digest(pending.token, token):
            raise PermissionError("invalid camera upload token")
        if not image or len(image) > self.max_image_size:
            raise ValueError("invalid camera image size")
        if not image.startswith(b"\xff\xd8") or not image.endswith(b"\xff\xd9"):
            raise ValueError("camera upload is not a JPEG image")
        if pending.ready.is_set():
            raise ValueError("camera image already uploaded")
        pending.image = image
        pending.ready.set()


camera_snapshot_service = CameraSnapshotService()
