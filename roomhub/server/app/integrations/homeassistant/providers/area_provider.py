import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ....core.event_bus import event_bus
from ....events.entity_events import AreaDiscoveredEvent


logger = logging.getLogger(__name__)


class HomeAssistantAreaProvider:

    def __init__(self, send_request: Callable[[dict[str, Any]], Awaitable[Any]]) -> None:
        self._send_request = send_request

    async def sync(self) -> None:
        areas = await self._send_request({"type": "config/area_registry/list"})

        for area in areas:
            await event_bus.publish(
                AreaDiscoveredEvent(
                    area_id=area["area_id"],
                    name=area["name"],
                    floor_id=area.get("floor_id")
                )
            )

        logger.info("Imported %s Home Assistant areas", len(areas))
