#!/usr/bin/env python3
"""Prepare RoomHub's memory-bounded ESP32-C6 ESP-Hosted firmware tree."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


SOURCE_QUEUE = "#define SDIO_SLAVE_QUEUE_SIZE            20"
ROOMHUB_QUEUE = "#define SDIO_SLAVE_QUEUE_SIZE            5"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    destination = args.destination.resolve()
    if not (source / "main" / "sdio_slave_api.c").is_file():
        raise SystemExit(f"ESP-Hosted slave project not found: {source}")

    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)

    driver = destination / "main" / "sdio_slave_api.c"
    contents = driver.read_text(encoding="utf-8")
    if contents.count(SOURCE_QUEUE) != 1:
        raise SystemExit("Unexpected ESP-Hosted SDIO queue definition")
    driver.write_text(contents.replace(SOURCE_QUEUE, ROOMHUB_QUEUE), encoding="utf-8")

    defaults = destination / "sdkconfig.defaults.esp32c6"
    with defaults.open("a", encoding="utf-8") as stream:
        stream.write(
            "\n# RoomHub keeps streaming mode but bounds the C6-to-P4 DMA burst.\n"
            "CONFIG_ESP_SDIO_STREAMING_MODE=y\n"
        )

    # 1.4.1 identifies the RoomHub queue-bounded derivative of upstream 1.4.0.
    (destination / "main" / "coprocessor_fw_version.txt").write_text(
        "1.4.1\n", encoding="utf-8"
    )

    print(f"Prepared RoomHub ESP32-C6 firmware at {destination}")


if __name__ == "__main__":
    main()
