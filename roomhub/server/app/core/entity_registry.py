from ..models.entity import Entity
from .entity_state import EntityState
from .database import get_connection


class EntityRegistry:

    def __init__(self):

        self.entities = {}

        self.states = {}


    def register(self, entity: Entity):

        self.entities[
            entity.entity_id
        ] = entity

        self.states[
            entity.entity_id
        ] = EntityState()

        self.save(entity)


    def get(self, entity_id):

        return self.entities.get(
            entity_id
        )


    def save(self, entity):

        connection = get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO entities
            (
                entity_id,
                entity_type,
                name
            )
            VALUES (?, ?, ?)
            """,
            (
                entity.entity_id,
                entity.entity_type,
                entity.name
            )
        )

        connection.commit()

        connection.close()


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


entity_registry = EntityRegistry()