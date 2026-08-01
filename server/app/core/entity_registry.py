from ..models.entity import Entity


class EntityRegistry:

    def __init__(self):
        self.entities = {}


    def register(self, entity: Entity):

        self.entities[entity.entity_id] = entity


    def get(self, entity_id):

        return self.entities.get(entity_id)


    def get_all(self):

        return {
            key: value.model_dump()
            for key, value in self.entities.items()
        }


entity_registry = EntityRegistry()