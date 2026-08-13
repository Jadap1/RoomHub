from homeassistant.components.switch import SwitchEntity

from .entity import RoomHubEndpointEntity, async_setup_endpoint_entities


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_endpoint_entities(entry, async_add_entities, RoomHubScreenSwitch)


class RoomHubScreenSwitch(RoomHubEndpointEntity, SwitchEntity):
    _attr_name = "Screen"

    def __init__(self, coordinator, endpoint_id: str) -> None:
        super().__init__(coordinator, endpoint_id)
        self._attr_unique_id = f"{endpoint_id}_screen"

    @property
    def is_on(self) -> bool | None:
        return self.endpoint.get("state", {}).get("controls", {}).get("screen_on")

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.api.control(self.endpoint_id, screen_on=True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.api.control(self.endpoint_id, screen_on=False)
        await self.coordinator.async_request_refresh()
