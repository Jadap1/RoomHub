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

    device_id: str | None = None
    area_id: str | None = None

    platform: str | None = None
    entity_category: str | None = None

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
class FloorDiscoveredEvent(BaseModel):
    floor_id: str
    name: str
    level: int | None = None


class AreaDiscoveredEvent(BaseModel):
    area_id: str
    name: str
    floor_id: str | None = None


class DeviceDiscoveredEvent(BaseModel):
    device_id: str
    name: str
    area_id: str | None = None

    manufacturer: str | None = None
    model: str | None = None

    config_entries: list[str] = Field(
        default_factory=list
    )

    via_device_id: str | None = None