from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class RoomHubEndpointEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, endpoint_id: str) -> None:
        super().__init__(coordinator)
        self.endpoint_id = endpoint_id

    @property
    def endpoint(self) -> dict:
        return self.coordinator.data.get(self.endpoint_id, {})

    @property
    def available(self) -> bool:
        return bool(self.endpoint.get("connected")) and self.coordinator.last_update_success

    @property
    def device_info(self) -> DeviceInfo:
        endpoint = self.endpoint
        return DeviceInfo(
            identifiers={(DOMAIN, self.endpoint_id)},
            name=endpoint.get("device_name", self.endpoint_id),
            manufacturer="RoomHub",
            model="M5Stack Tab5",
            sw_version=endpoint.get("firmware_version"),
            suggested_area=endpoint.get("room"),
        )


def endpoint_ids(coordinator) -> list[str]:
    return sorted(coordinator.data)


def async_setup_endpoint_entities(entry, async_add_entities, entity_class) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new_endpoints() -> None:
        new_ids = set(endpoint_ids(coordinator)) - known
        if new_ids:
            async_add_entities(entity_class(coordinator, item) for item in sorted(new_ids))
            known.update(new_ids)

    add_new_endpoints()
    entry.async_on_unload(coordinator.async_add_listener(add_new_endpoints))
