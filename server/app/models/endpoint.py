from datetime import datetime
from pydantic import BaseModel, Field


class Endpoint(BaseModel):

    device_id: str
    device_name: str
    room: str
    capabilities: list[str]

    connected: bool = False
    last_seen: datetime | None = None
    state: dict = Field(default_factory=dict)