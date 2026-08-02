from ..events.entity_events import (
    AreaDiscoveredEvent,
)
from ..models.area import Area


class AreaRegistry:

    def __init__(self) -> None:
        self.areas: dict[str, Area] = {}


    def get(
        self,
        area_id: str
    ) -> Area | None:

        return self.areas.get(area_id)


    def get_all(self) -> dict[str, dict]:

        return {
            key: value.model_dump()
            for key, value in self.areas.items()
        }


    async def handle_discovered(
        self,
        event: AreaDiscoveredEvent
    ) -> None:

        self.areas[event.area_id] = Area(
            area_id=event.area_id,
            name=event.name,
            floor_id=event.floor_id,
        )


area_registry = AreaRegistry()
