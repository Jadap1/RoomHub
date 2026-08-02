import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ....core.event_bus import event_bus
from ....events.entity_events import DeviceDiscoveredEvent


logger = logging.getLogger(__name__)


class HomeAssistantDeviceProvider:

    def __init__(self, send_request: Callable[[dict[str, Any]], Awaitable[Any]]) -> None:
        self._send_request = send_request

    async def sync(self) -> None:
        devices = await self._send_request({"type": "config/device_registry/list"})

        for device in devices:
            device_id = device["id"]
            name = device.get("name_by_user") or device.get("name") or device_id

            await event_bus.publish(
                DeviceDiscoveredEvent(
                    device_id=device_id,
                    name=name,
                    area_id=device.get("area_id"),
                    manufacturer=device.get("manufacturer"),
                    model=device.get("model"),
                    config_entries=device.get("config_entries") or [],
                    via_device_id=device.get("via_device_id")
                )
            )

        logger.info("Imported %s Home Assistant devices", len(devices))
