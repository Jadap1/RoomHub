from homeassistant.components.sensor import SensorEntity

from .entity import RoomHubEndpointEntity, async_setup_endpoint_entities


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_endpoint_entities(entry, async_add_entities, RoomHubFirmwareSensor)


class RoomHubFirmwareSensor(RoomHubEndpointEntity, SensorEntity):
    _attr_name = "Firmware"
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator, endpoint_id: str) -> None:
        super().__init__(coordinator, endpoint_id)
        self._attr_unique_id = f"{endpoint_id}_firmware"

    @property
    def native_value(self) -> str | None:
        return self.endpoint.get("firmware_version")
