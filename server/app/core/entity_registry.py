from ..models.entity import Entity
from .database import get_connection


class EntityRegistry:


    def __init__(self):

        self.entities = {}


    def register(self, entity: Entity):

        self.entities[
            entity.entity_id
        ] = entity

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
                name,
                state
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                entity.entity_id,
                entity.entity_type,
                entity.name,
                entity.state
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
                name,
                state
            FROM entities
            """
        ).fetchall()

        connection.close()

        for row in rows:

            entity = Entity(
                entity_id=row[0],
                entity_type=row[1],
                name=row[2],
                state=row[3]
            )

            self.entities[entity.entity_id] = entity
entity_registry = EntityRegistry()