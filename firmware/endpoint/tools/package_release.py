#!/usr/bin/env python3
"""Create signed RoomHub OTA and complete Tab5 factory release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
BUILD = PROJECT / "build"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", type=Path, required=True, help="RSA-3072 signing key")
    parser.add_argument("--version", required=True, help="semantic firmware version")
    parser.add_argument(
        "--download-base-url",
        required=True,
        help="release URL containing the generated artifacts",
    )
    parser.add_argument("--output", type=Path, default=PROJECT / "dist")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    idf_path = Path(os.environ.get("IDF_PATH", ""))
    if not idf_path.is_dir():
        raise RuntimeError("Activate ESP-IDF so IDF_PATH is available")

    key = require_file(args.key.resolve(), "signing key")
    unsigned_app = require_file(BUILD / "roomhub_endpoint.bin", "built application")
    flash_config = json.loads(
        require_file(BUILD / "flasher_args.json", "flash layout").read_text()
    )

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    ota_name = f"roomhub-tab5-{args.version}-ota.bin"
    factory_name = f"roomhub-tab5-{args.version}-factory.bin"
    ota_path = output / ota_name
    factory_path = output / factory_name

    espsecure = idf_path / "components" / "esptool_py" / "esptool" / "espsecure.py"
    esptool = idf_path / "components" / "esptool_py" / "esptool" / "esptool.py"
    require_file(espsecure, "espsecure")
    require_file(esptool, "esptool")

    run([
        sys.executable,
        str(espsecure),
        "sign_data",
        "--version",
        "2",
        "--keyfile",
        str(key),
        "--output",
        str(ota_path),
        str(unsigned_app),
    ])

    app_partition_size = 4 * 1024 * 1024
    if ota_path.stat().st_size > app_partition_size:
        raise RuntimeError("signed application exceeds the 4 MiB OTA partition")

    merge_args = [
        sys.executable,
        str(esptool),
        "--chip",
        "esp32p4",
        "merge_bin",
        "-o",
        str(factory_path),
        "--flash_mode",
        flash_config["flash_settings"]["flash_mode"],
        "--flash_freq",
        flash_config["flash_settings"]["flash_freq"],
        "--flash_size",
        "16MB",
    ]
    for offset, relative in flash_config["flash_files"].items():
        source = ota_path if relative == "roomhub_endpoint.bin" else BUILD / relative
        merge_args.extend([offset, str(require_file(source, relative))])
    run(merge_args)

    base_url = args.download_base_url.rstrip("/")
    browser_manifest = {
        "name": "RoomHub for M5Stack Tab5",
        "version": args.version,
        "new_install_prompt_erase": True,
        "builds": [
            {
                "chipFamily": "ESP32-P4",
                "parts": [{"path": f"{base_url}/{factory_name}", "offset": 0}],
            }
        ],
    }
    (output / "manifest.json").write_text(
        json.dumps(browser_manifest, indent=2) + "\n", encoding="utf-8"
    )

    artifacts = [ota_path, factory_path, output / "manifest.json"]
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in artifacts),
        encoding="utf-8",
    )
    shutil.copy2(BUILD / "flasher_args.json", output / "flasher_args.json")
    print(f"Release artifacts written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
