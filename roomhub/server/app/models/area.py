from pydantic import BaseModel


class Area(BaseModel):
    area_id: str
    name: str
    floor_id: str | None = None
