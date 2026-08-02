from ..events.entity_events import (
    DeviceDiscoveredEvent,
)
from ..models.device import Device


class DeviceRegistry:

    def __init__(self) -> None:
        self.devices: dict[str, Device] = {}


    def get(
        self,
        device_id: str
    ) -> Device | None:

        return self.devices.get(device_id)


    def get_all(self) -> dict[str, dict]:

        return {
            key: value.model_dump()
            for key, value in self.devices.items()
        }


    async def handle_discovered(
        self,
        event: DeviceDiscoveredEvent
    ) -> None:

        self.devices[event.device_id] = Device(
            device_id=event.device_id,
            name=event.name,
            area_id=event.area_id,
            manufacturer=event.manufacturer,
            model=event.model,
            config_entries=event.config_entries,
            via_device_id=event.via_device_id
        )


device_registry = DeviceRegistry()