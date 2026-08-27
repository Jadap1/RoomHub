"""Copy release firmware beside the installer and make manifest paths local."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse


def prepare(release_dir: Path, installer_dir: Path) -> None:
    manifest_path = release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    copied = 0
    for build in manifest.get("builds", []):
        for part in build.get("parts", []):
            remote_path = str(part.get("path", ""))
            filename = Path(urlparse(remote_path).path).name
            if not filename or filename in {".", ".."}:
                raise ValueError(f"invalid firmware path: {remote_path!r}")
            source = release_dir / filename
            if not source.is_file():
                raise FileNotFoundError(f"release asset not downloaded: {filename}")
            shutil.copy2(source, installer_dir / filename)
            part["path"] = filename
            copied += 1
    if copied == 0:
        raise ValueError("manifest contains no firmware parts")
    (installer_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("installer_dir", type=Path)
    args = parser.parse_args()
    prepare(args.release_dir, args.installer_dir)


if __name__ == "__main__":
    main()
