from pydantic import BaseModel
from typing import List


class Endpoint(BaseModel):

    device_id: str
    device_name: str
    room: str
    capabilities: List[str]
    connected: bool = False
    