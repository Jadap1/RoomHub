from contextlib import closing

from ..events.entity_events import (
    FloorDiscoveredEvent,
    FloorRemovedEvent,
)
from ..models.floor import Floor
from .database import get_connection


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


    def load(self) -> None:

        with closing(get_connection()) as connection, connection:
            rows = connection.execute(
                "SELECT floor_id, name, level "
                "FROM floors"
            ).fetchall()

        self.floors = {
            row[0]: Floor(
                floor_id=row[0],
                name=row[1],
                level=row[2]
            )
            for row in rows
        }


    def save(self, floor: Floor) -> None:

        with closing(get_connection()) as connection, connection:
            connection.execute(
                """
                INSERT INTO floors (floor_id, name, level)
                VALUES (?, ?, ?)
                ON CONFLICT(floor_id) DO UPDATE SET
                    name = excluded.name,
                    level = excluded.level
                """,
                (floor.floor_id, floor.name, floor.level)
            )


    async def handle_discovered(
        self,
        event: FloorDiscoveredEvent
    ) -> None:

        floor = Floor(
            floor_id=event.floor_id,
            name=event.name,
            level=event.level
        )
        self.floors[event.floor_id] = floor
        self.save(floor)


    async def handle_removed(
        self,
        event: FloorRemovedEvent
    ) -> None:

        self.floors.pop(
            event.floor_id,
            None
        )

        with closing(get_connection()) as connection, connection:
            connection.execute(
                "DELETE FROM floors WHERE floor_id = ?",
                (event.floor_id,)
            )


floor_registry = FloorRegistry()
