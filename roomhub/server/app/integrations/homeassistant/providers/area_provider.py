import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ....core.event_bus import event_bus
from ....core.area_registry import area_registry
from ....events.entity_events import AreaDiscoveredEvent, AreaRemovedEvent


logger = logging.getLogger(__name__)


class HomeAssistantAreaProvider:

    def __init__(self, send_request: Callable[[dict[str, Any]], Awaitable[Any]]) -> None:
        self._send_request = send_request
        self._known_ids: set[str] = set()

    async def sync(self) -> None:
        areas = await self._send_request({"type": "config/area_registry/list"})
        current_ids = {area["area_id"] for area in areas}
        known_ids = self._known_ids or set(
            area_registry.areas
        )

        for area_id in known_ids - current_ids:
            await event_bus.publish(AreaRemovedEvent(area_id=area_id))

        for area in areas:
            await event_bus.publish(
                AreaDiscoveredEvent(
                    area_id=area["area_id"],
                    name=area["name"],
                    floor_id=area.get("floor_id")
                )
            )

        self._known_ids = current_ids

        logger.info("Imported %s Home Assistant areas", len(areas))
