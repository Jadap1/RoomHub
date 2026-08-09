import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


MAX_FIRMWARE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class FirmwareManifest:
    version: str
    size: int
    sha256: str
    path: str = "/firmware/endpoint/image"


class FirmwareService:
    def __init__(self, directory: str | Path | None = None):
        configured = directory or os.getenv(
            "ROOMHUB_FIRMWARE_PATH",
            "/data/firmware",
        )
        self.directory = Path(configured)
        self.image_path = self.directory / "roomhub_endpoint.bin"
        self.manifest_path = self.directory / "manifest.json"

    def publish(self, version: str, image: bytes) -> FirmwareManifest:
        clean_version = version.strip()
        if not clean_version or len(clean_version) > 32:
            raise ValueError("invalid firmware version")
        if not image or len(image) > MAX_FIRMWARE_BYTES:
            raise ValueError("invalid firmware size")
        if image[0] != 0xE9:
            raise ValueError("not an ESP application image")

        manifest = FirmwareManifest(
            version=clean_version,
            size=len(image),
            sha256=hashlib.sha256(image).hexdigest(),
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary_image = self.image_path.with_suffix(".bin.tmp")
        temporary_manifest = self.manifest_path.with_suffix(".json.tmp")
        temporary_image.write_bytes(image)
        temporary_manifest.write_text(
            json.dumps(asdict(manifest), indent=2),
            encoding="utf-8",
        )
        temporary_image.replace(self.image_path)
        temporary_manifest.replace(self.manifest_path)
        return manifest

    def manifest(self) -> FirmwareManifest | None:
        if not self.manifest_path.exists() or not self.image_path.exists():
            return None
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest = FirmwareManifest(**data)
        if self.image_path.stat().st_size != manifest.size:
            return None
        return manifest


firmware_service = FirmwareService()
