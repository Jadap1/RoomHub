from pydantic import BaseModel
from typing import List


class Entity(BaseModel):

    entity_id: str
    entity_type: str
    name: str
    state: str = "off"
    capabilities: List[str] = []