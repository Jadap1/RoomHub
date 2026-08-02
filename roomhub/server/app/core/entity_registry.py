from contextlib import closing, contextmanager
from datetime import datetime
import json

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

        self._batch_connection = None


    @contextmanager
    def persistence_batch(self):

        if self._batch_connection is not None:
            yield
            return

        with closing(get_connection()) as connection, connection:
            self._batch_connection = connection
            try:
                yield
            finally:
                self._batch_connection = None


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

        self._execute_write(
            """
            INSERT INTO entities
            (
                entity_id, entity_type, name,
                integration, device_id, area_id,
                platform, entity_category
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                entity_type = excluded.entity_type,
                name = excluded.name,
                integration = excluded.integration,
                device_id = excluded.device_id,
                area_id = excluded.area_id,
                platform = excluded.platform,
                entity_category = excluded.entity_category
            """,
            (
                entity.entity_id,
                entity.entity_type,
                entity.name,
                entity.integration,
                entity.device_id,
                entity.area_id,
                entity.platform,
                entity.entity_category
            )
        )


    def _execute_write(
        self,
        statement,
        parameters
    ):

        if self._batch_connection is not None:
            self._batch_connection.execute(
                statement,
                parameters
            )
            return

        with closing(get_connection()) as connection, connection:
            connection.execute(
                statement,
                parameters
            )

    def get_all(self):

        return {
            key: value.model_dump()
            for key, value in self.entities.items()
        }


    def load(self):

        self.entities = {}
        self.states = {}

        connection = get_connection()

        cursor = connection.cursor()

        rows = cursor.execute(
            """
            SELECT
                entity_id,
                entity_type,
                name,
                integration,
                device_id,
                area_id,
                platform,
                entity_category
            FROM entities
            """
        ).fetchall()

        connection.close()

        for row in rows:

            entity = Entity(
                entity_id=row[0],
                entity_type=row[1],
                name=row[2],
                integration=row[3] or "homeassistant",
                device_id=row[4],
                area_id=row[5],
                platform=row[6],
                entity_category=row[7]
            )

            self.entities[
                entity.entity_id
            ] = entity

            self.states[
                entity.entity_id
            ] = EntityState()

        connection = get_connection()
        state_rows = connection.execute(
            """
            SELECT entity_id, state, attributes,
                   available, last_updated
            FROM entity_states
            """
        ).fetchall()
        connection.close()

        for row in state_rows:

            if row[0] not in self.entities:
                continue

            self.states[row[0]] = EntityState(
                state=row[1],
                attributes=json.loads(row[2]),
                available=bool(row[3]),
                last_updated=datetime.fromisoformat(
                    row[4]
                )
            )


    def update_state(
        self,
        entity_id,
        state,
        attributes=None,
        available=None
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

        if available is not None:
            self.states[
                entity_id
            ].available = available


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

        state = self.states.get(entity_id)

        if state is None:
            return

        self._execute_write(
            """
            INSERT INTO entity_states
            (
                entity_id, state, attributes,
                available, last_updated
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                state = excluded.state,
                attributes = excluded.attributes,
                available = excluded.available,
                last_updated = excluded.last_updated
            """,
            (
                entity_id,
                state.state,
                json.dumps(state.attributes),
                int(state.available),
                state.last_updated.isoformat()
            )
        )
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
            attributes=event.attributes,
            available=event.available
        )


entity_registry = EntityRegistry()
