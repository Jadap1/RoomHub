#!/usr/bin/env python3
"""Fail when tracked RoomHub files contain local secrets or private keys."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATHS = {"roomhub/server/config/homeassistant.json"}
FORBIDDEN_SUFFIXES = {".key", ".p12", ".pfx", ".pem"}
PATTERNS = {
    "Home Assistant JWT": re.compile(
        r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
    ),
    "private key": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
}


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [item.decode() for item in result.stdout.split(b"\0") if item]


def main() -> int:
    failures: list[str] = []
    for relative in tracked_files():
        normalized = relative.replace("\\", "/")
        path = ROOT / relative
        if normalized in FORBIDDEN_PATHS:
            failures.append(f"tracked local-secret file: {normalized}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"tracked key file: {normalized}")
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                failures.append(f"{label} found in: {normalized}")

    if failures:
        print("Repository secret check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Repository secret check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
