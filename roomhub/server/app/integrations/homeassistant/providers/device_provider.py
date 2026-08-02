import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ....core.event_bus import event_bus
from ....events.entity_events import DeviceDiscoveredEvent, DeviceRemovedEvent


logger = logging.getLogger(__name__)


class HomeAssistantDeviceProvider:

    def __init__(self, send_request: Callable[[dict[str, Any]], Awaitable[Any]]) -> None:
        self._send_request = send_request
        self._known_ids: set[str] = set()

    async def sync(self) -> None:
        devices = await self._send_request({"type": "config/device_registry/list"})
        current_ids = {device["id"] for device in devices}

        for device_id in self._known_ids - current_ids:
            await event_bus.publish(DeviceRemovedEvent(device_id=device_id))

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

        self._known_ids = current_ids

        logger.info("Imported %s Home Assistant devices", len(devices))
