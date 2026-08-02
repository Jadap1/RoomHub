from contextlib import closing

from ..events.entity_events import (
    AreaDiscoveredEvent,
    AreaRemovedEvent,
)
from ..models.area import Area
from .database import get_connection


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


    def load(self) -> None:

        with closing(get_connection()) as connection, connection:
            rows = connection.execute(
                "SELECT area_id, name, floor_id "
                "FROM areas"
            ).fetchall()

        self.areas = {
            row[0]: Area(
                area_id=row[0],
                name=row[1],
                floor_id=row[2]
            )
            for row in rows
        }


    def save(self, area: Area) -> None:

        with closing(get_connection()) as connection, connection:
            connection.execute(
                """
                INSERT INTO areas (area_id, name, floor_id)
                VALUES (?, ?, ?)
                ON CONFLICT(area_id) DO UPDATE SET
                    name = excluded.name,
                    floor_id = excluded.floor_id
                """,
                (area.area_id, area.name, area.floor_id)
            )


    async def handle_discovered(
        self,
        event: AreaDiscoveredEvent
    ) -> None:

        area = Area(
            area_id=event.area_id,
            name=event.name,
            floor_id=event.floor_id,
        )
        self.areas[event.area_id] = area
        self.save(area)


    async def handle_removed(
        self,
        event: AreaRemovedEvent
    ) -> None:

        self.areas.pop(
            event.area_id,
            None
        )

        with closing(get_connection()) as connection, connection:
            connection.execute(
                "DELETE FROM areas WHERE area_id = ?",
                (event.area_id,)
            )


area_registry = AreaRegistry()
