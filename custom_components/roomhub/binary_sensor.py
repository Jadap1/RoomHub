from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .entity import RoomHubEndpointEntity, async_setup_endpoint_entities


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_endpoint_entities(entry, async_add_entities, RoomHubConnectionSensor)


class RoomHubConnectionSensor(RoomHubEndpointEntity, BinarySensorEntity):
    _attr_name = "Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, endpoint_id: str) -> None:
        super().__init__(coordinator, endpoint_id)
        self._attr_unique_id = f"{endpoint_id}_connected"

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool:
        return bool(self.endpoint.get("connected"))
