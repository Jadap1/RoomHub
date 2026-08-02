from typing import Any

from pydantic import BaseModel, Field


class EntityCommandEvent(BaseModel):

    entity_id: str
    command: str
    data: dict[str, Any] = Field(default_factory=dict)