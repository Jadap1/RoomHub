#!/usr/bin/env python3
"""Provision a RoomHub endpoint over its USB Serial/JTAG connection."""

from __future__ import annotations

import argparse
import getpass
import sys
import time
from dataclasses import dataclass

import serial


START_REQUEST = b"ROOMHUB_PROVISION 1\n"
FIELD_PREFIX = "ROOMHUB_FIELD "
RESULT_PREFIX = "ROOMHUB_RESULT "


@dataclass(frozen=True)
class ProvisioningValues:
    endpoint_id: str
    roomhub_url: str
    wifi_ssid: str
    wifi_password: str
    device_token: str


def collect_values() -> ProvisioningValues:
    print("Enter the endpoint settings. The Wi-Fi password will remain hidden.")
    return ProvisioningValues(
        endpoint_id=input("Endpoint ID: ").strip(),
        roomhub_url=input("RoomHub URL: ").strip(),
        device_token=getpass.getpass("Pairing credential: "),
        wifi_ssid=input("Wi-Fi network name: "),
        wifi_password=getpass.getpass("Wi-Fi password: "),
    )


def provision(port: str, values: ProvisioningValues, timeout: float) -> None:
    fields = {
        "endpoint_id": values.endpoint_id,
        "roomhub_url": values.roomhub_url,
        "device_token": values.device_token,
        "wifi_ssid": values.wifi_ssid,
        "wifi_password": values.wifi_password,
    }

    with serial.Serial(port, 115200, timeout=1, write_timeout=5) as connection:
        time.sleep(0.5)
        connection.reset_input_buffer()
        connection.write(START_REQUEST)
        connection.flush()

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw_line = connection.readline()
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line.startswith(FIELD_PREFIX):
                field_name = line.removeprefix(FIELD_PREFIX)
                if field_name not in fields:
                    raise RuntimeError(f"Device requested unknown field: {field_name}")
                connection.write(fields[field_name].encode("utf-8") + b"\n")
                connection.flush()
            elif line.startswith(RESULT_PREFIX):
                result = line.removeprefix(RESULT_PREFIX)
                if result == "saved":
                    return
                raise RuntimeError(f"Provisioning failed: {result}")

    raise TimeoutError(
        "The endpoint did not complete provisioning. Reset it and try again."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM3", help="USB serial port (default: COM3)")
    parser.add_argument(
        "--timeout",
        type=float,
        default=30,
        help="Seconds to wait for the endpoint (default: 30)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    values = collect_values()
    try:
        provision(args.port, values, args.timeout)
    except (OSError, RuntimeError, TimeoutError, serial.SerialException) as error:
        print(f"Setup failed: {error}", file=sys.stderr)
        return 1

    print("Configuration saved. The endpoint is restarting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
