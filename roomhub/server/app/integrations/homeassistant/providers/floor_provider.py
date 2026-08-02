import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ....core.event_bus import event_bus
from ....events.entity_events import FloorDiscoveredEvent


logger = logging.getLogger(__name__)


class HomeAssistantFloorProvider:

    def __init__(self, send_request: Callable[[dict[str, Any]], Awaitable[Any]]) -> None:
        self._send_request = send_request

    async def sync(self) -> None:
        floors = await self._send_request({"type": "config/floor_registry/list"})

        for floor in floors:
            await event_bus.publish(
                FloorDiscoveredEvent(
                    floor_id=floor["floor_id"],
                    name=floor["name"],
                    level=floor.get("level")
                )
            )

        logger.info("Imported %s Home Assistant floors", len(floors))
