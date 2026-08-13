from homeassistant.components.camera import Camera

from .api import RoomHubApiError
from .entity import RoomHubEndpointEntity, async_setup_endpoint_entities


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_endpoint_entities(
        entry, async_add_entities, RoomHubCamera, required_capability="camera"
    )


class RoomHubCamera(RoomHubEndpointEntity, Camera):
    _attr_name = "Camera"
    _attr_is_streaming = False

    def __init__(self, coordinator, endpoint_id: str) -> None:
        Camera.__init__(self)
        RoomHubEndpointEntity.__init__(self, coordinator, endpoint_id)
        self._attr_unique_id = f"{endpoint_id}_camera"

    async def async_camera_image(self, width=None, height=None) -> bytes | None:
        try:
            return await self.coordinator.api.camera_image(self.endpoint_id)
        except RoomHubApiError:
            return None
