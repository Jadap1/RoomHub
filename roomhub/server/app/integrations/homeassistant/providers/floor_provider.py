import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ....core.event_bus import event_bus
from ....core.floor_registry import floor_registry
from ....events.entity_events import FloorDiscoveredEvent, FloorRemovedEvent


logger = logging.getLogger(__name__)


class HomeAssistantFloorProvider:

    def __init__(self, send_request: Callable[[dict[str, Any]], Awaitable[Any]]) -> None:
        self._send_request = send_request
        self._known_ids: set[str] = set()

    async def sync(self) -> None:
        floors = await self._send_request({"type": "config/floor_registry/list"})
        current_ids = {floor["floor_id"] for floor in floors}
        known_ids = self._known_ids or set(
            floor_registry.floors
        )

        for floor_id in known_ids - current_ids:
            await event_bus.publish(FloorRemovedEvent(floor_id=floor_id))

        for floor in floors:
            await event_bus.publish(
                FloorDiscoveredEvent(
                    floor_id=floor["floor_id"],
                    name=floor["name"],
                    level=floor.get("level")
                )
            )

        self._known_ids = current_ids

        logger.info("Imported %s Home Assistant floors", len(floors))
