from pydantic import BaseModel, Field


class Entity(BaseModel):
    entity_id: str
    entity_type: str
    name: str

    integration: str = "homeassistant"

    device_id: str | None = None
    area_id: str | None = None

    platform: str | None = None
    entity_category: str | None = None

    capabilities: list[str] = Field(
        default_factory=list
    )