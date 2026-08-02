from typing import Any

from pydantic import BaseModel, Field


class EntityCommandEvent(BaseModel):

    entity_id: str
    command: str
    data: dict[str, Any] = Field(
        default_factory=dict
    )


class EntityDiscoveredEvent(BaseModel):

    entity_id: str
    entity_type: str
    name: str
    attributes: dict[str, Any] = Field(
        default_factory=dict
    )


class EntityStateChangedEvent(BaseModel):

    entity_id: str
    state: str
    attributes: dict[str, Any] = Field(
        default_factory=dict
    )

    available: bool = True