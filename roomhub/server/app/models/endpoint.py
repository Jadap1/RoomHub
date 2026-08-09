from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional

class Endpoint(BaseModel):

    device_id: str
    device_name: str
    room: str
    area_id: str | None = None
    capabilities: list[str]

    connected: bool = False
    last_seen: datetime | None = None
    state: dict = {}
