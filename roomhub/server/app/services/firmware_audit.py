import json
import os
from datetime import UTC, datetime
from pathlib import Path


class FirmwareAuditLog:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv(
            "ROOMHUB_FIRMWARE_AUDIT_PATH",
            "/data/firmware-audit.jsonl",
        ))

    def record(self, action: str, **details) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "action": action,
            **details,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, separators=(",", ":")) + "\n")


firmware_audit = FirmwareAuditLog()
