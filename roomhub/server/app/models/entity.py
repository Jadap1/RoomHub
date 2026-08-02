from pydantic import BaseModel


class Entity(BaseModel):

    entity_id: str
    entity_type: str
    name: str
    capabilities: list[str] = []
    integration: str = "homeassistant"