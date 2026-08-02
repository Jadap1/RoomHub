from pydantic import BaseModel, Field


class Device(BaseModel):
    device_id: str
    name: str
    area_id: str | None = None

    manufacturer: str | None = None
    model: str | None = None

    config_entries: list[str] = Field(
        default_factory=list
    )

    via_device_id: str | None = None