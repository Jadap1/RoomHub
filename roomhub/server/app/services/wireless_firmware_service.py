import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


MAX_WIRELESS_FIRMWARE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class WirelessFirmwareManifest:
    version: str
    size: int
    sha256: str
    path: str = "/firmware/wireless/image"


class WirelessFirmwareService:
    def __init__(self, directory: str | Path | None = None):
        root = Path(directory or os.getenv("ROOMHUB_FIRMWARE_PATH", "/data/firmware"))
        self.directory = root / "wireless"
        self.image_path = self.directory / "network_adapter.bin"
        self.manifest_path = self.directory / "manifest.json"

    def publish(self, version: str, image: bytes) -> WirelessFirmwareManifest:
        clean_version = version.strip()
        if not clean_version or len(clean_version) > 32:
            raise ValueError("invalid wireless firmware version")
        if not image or len(image) > MAX_WIRELESS_FIRMWARE_BYTES:
            raise ValueError("invalid wireless firmware size")
        if image[0] != 0xE9:
            raise ValueError("not an ESP application image")
        manifest = WirelessFirmwareManifest(
            version=clean_version,
            size=len(image),
            sha256=hashlib.sha256(image).hexdigest(),
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary_image = self.image_path.with_suffix(".bin.tmp")
        temporary_manifest = self.manifest_path.with_suffix(".json.tmp")
        temporary_image.write_bytes(image)
        temporary_manifest.write_text(
            json.dumps(asdict(manifest), indent=2), encoding="utf-8"
        )
        temporary_image.replace(self.image_path)
        temporary_manifest.replace(self.manifest_path)
        return manifest

    def manifest(self) -> WirelessFirmwareManifest | None:
        if not self.manifest_path.exists() or not self.image_path.exists():
            return None
        manifest = WirelessFirmwareManifest(**json.loads(
            self.manifest_path.read_text(encoding="utf-8")
        ))
        if self.image_path.stat().st_size != manifest.size:
            return None
        if hashlib.sha256(self.image_path.read_bytes()).hexdigest() != manifest.sha256:
            return None
        return manifest


wireless_firmware_service = WirelessFirmwareService()
