from ..events.entity_events import (
    FloorDiscoveredEvent,
    FloorRemovedEvent,
)
from ..models.floor import Floor


class FloorRegistry:

    def __init__(self) -> None:
        self.floors: dict[str, Floor] = {}


    def get(
        self,
        floor_id: str
    ) -> Floor | None:

        return self.floors.get(floor_id)


    def get_all(self) -> dict[str, dict]:

        return {
            key: value.model_dump()
            for key, value in self.floors.items()
        }


    async def handle_discovered(
        self,
        event: FloorDiscoveredEvent
    ) -> None:

        self.floors[event.floor_id] = Floor(
            floor_id=event.floor_id,
            name=event.name,
            level=event.level
        )


    async def handle_removed(
        self,
        event: FloorRemovedEvent
    ) -> None:

        self.floors.pop(
            event.floor_id,
            None
        )


floor_registry = FloorRegistry()
