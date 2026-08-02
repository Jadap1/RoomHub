from pydantic import BaseModel


class Floor(BaseModel):
    floor_id: str
    name: str
    level: int | None = None