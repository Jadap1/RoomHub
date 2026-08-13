from homeassistant.components.number import NumberEntity, NumberMode

from .entity import RoomHubEndpointEntity, async_setup_endpoint_entities


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_endpoint_entities(entry, async_add_entities, RoomHubVolumeNumber)


class RoomHubVolumeNumber(RoomHubEndpointEntity, NumberEntity):
    _attr_name = "Volume"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, endpoint_id: str) -> None:
        super().__init__(coordinator, endpoint_id)
        self._attr_unique_id = f"{endpoint_id}_volume"

    @property
    def native_value(self) -> float | None:
        return self.endpoint.get("state", {}).get("controls", {}).get("volume")

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.api.control(self.endpoint_id, volume=round(value))
        await self.coordinator.async_request_refresh()
