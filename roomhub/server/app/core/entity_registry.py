from ..models.entity import Entity
from .entity_state import EntityState
from .database import get_connection
from ..events.entity_events import (
    EntityDiscoveredEvent,
    EntityStateChangedEvent,
)


class EntityRegistry:

    def __init__(self):

        self.entities = {}

        self.states = {}


    def register(self, entity: Entity):

        self.entities[
            entity.entity_id
        ] = entity

        if entity.entity_id not in self.states:

            self.states[
                entity.entity_id
            ] = EntityState()

        self.save(entity)


    def get(self, entity_id):

        return self.entities.get(
            entity_id
        )


    def save(self, entity):

        with get_connection() as connection:

            connection.execute(
                """
                INSERT INTO entities
                (
                    entity_id,
                    entity_type,
                    name
                )
                VALUES (?, ?, ?)
                ON CONFLICT(entity_id)
                DO UPDATE SET
                    entity_type = excluded.entity_type,
                    name = excluded.name
                """,
                (
                    entity.entity_id,
                    entity.entity_type,
                    entity.name
                )
            )

        connection.commit()


    def get_all(self):

        return {
            key: value.model_dump()
            for key, value in self.entities.items()
        }


    def load(self):

        connection = get_connection()

        cursor = connection.cursor()

        rows = cursor.execute(
            """
            SELECT
                entity_id,
                entity_type,
                name
            FROM entities
            """
        ).fetchall()

        connection.close()

        for row in rows:

            entity = Entity(
                entity_id=row[0],
                entity_type=row[1],
                name=row[2]
            )

            self.entities[
                entity.entity_id
            ] = entity

            self.states[
                entity.entity_id
            ] = EntityState()


    def update_state(
        self,
        entity_id,
        state,
        attributes=None
    ):

        if entity_id not in self.states:

            self.states[
                entity_id
            ] = EntityState()


        self.states[
            entity_id
        ].update(
            state,
            attributes
        )


        self.save_state(
            entity_id
        )


    def get_state(self, entity_id):

        state = self.states.get(
            entity_id
        )

        if state:

            return state.as_dict()


        return None


    def save_state(self, entity_id):

        # Temporary placeholder.
        # We will add state persistence separately.

        pass
    async def handle_entity_discovered(
        self,
        event: EntityDiscoveredEvent
    ) -> None:

        existing = self.get(
            event.entity_id
        )

        if existing:

            existing.name = event.name
            existing.entity_type = event.entity_type
            existing.device_id = event.device_id
            existing.area_id = event.area_id
            existing.platform = event.platform
            existing.entity_category = (
                event.entity_category
            )

            self.save(existing)

            return


        self.register(
            Entity(
                entity_id=event.entity_id,
                entity_type=event.entity_type,
                name=event.name,
                integration="homeassistant",
                device_id=event.device_id,
                area_id=event.area_id,
                platform=event.platform,
                entity_category=event.entity_category
            )
        )


    async def handle_state_changed(
        self,
        event: EntityStateChangedEvent
    ) -> None:

        self.update_state(
            entity_id=event.entity_id,
            state=event.state,
            attributes=event.attributes
        )

        cached_state = self.states.get(
            event.entity_id
        )

        if cached_state:

            cached_state.available = (
                event.available
            )


entity_registry = EntityRegistry()
