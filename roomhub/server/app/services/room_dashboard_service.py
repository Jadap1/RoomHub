from ..core.area_registry import area_registry
from ..core.connection_manager import manager
from ..core.entity_registry import entity_registry
from ..core.registry import registry
from ..events.entity_events import EntityStateChangedEvent


SUPPORTED_ENTITY_TYPES = {"light", "switch", "climate"}
DISPLAY_ATTRIBUTES = {
    "brightness",
    "current_temperature",
    "hvac_action",
    "max_temp",
    "min_temp",
    "target_temp_step",
    "temperature",
}


class RoomDashboardService:
    def snapshot(
        self,
        area_id: str | None,
        maximum_entities: int = 30,
        excluded_entity_ids: set[str] | None = None,
    ) -> dict:
        area = area_registry.get(area_id) if area_id else None
        excluded_entity_ids = excluded_entity_ids or set()
        entities = []
        if area is not None:
            for entity in entity_registry.entities.values():
                if (
                    entity.area_id != area_id
                    or entity.entity_type not in SUPPORTED_ENTITY_TYPES
                    or entity.entity_category is not None
                    or entity.entity_id in excluded_entity_ids
                ):
                    continue
                state = entity_registry.get_state(entity.entity_id)
                compact_state = None
                if state is not None:
                    compact_state = {
                        "state": state.get("state"),
                        "available": state.get("available", True),
                        "attributes": {
                            key: value
                            for key, value in (state.get("attributes") or {}).items()
                            if key in DISPLAY_ATTRIBUTES
                        },
                    }
                entities.append({
                    "entity_id": entity.entity_id,
                    "entity_type": entity.entity_type,
                    "name": entity.name,
                    "action": "activate",
                    "state": compact_state,
                })
        entities.sort(key=lambda item: (item["entity_type"], item["name"].casefold()))
        return {
            "area_id": area_id,
            "area_name": area.name if area is not None else "Unassigned",
            "entities": entities[:maximum_entities],
        }

    @staticmethod
    def maximum_entities_for_firmware(firmware_version: str | None) -> int:
        try:
            major, minor, *_ = (
                int(part) for part in (firmware_version or "").split(".")
            )
        except (TypeError, ValueError):
            return 6
        return 30 if (major, minor) >= (0, 5) else 6

    async def send(self, endpoint_id: str) -> None:
        endpoint = registry.get(endpoint_id)
        if endpoint is None or not endpoint.connected:
            return
        # Imported here to avoid a module cycle between snapshot delivery and
        # preference updates.
        from .endpoint_dashboard_preferences_service import (
            endpoint_dashboard_preferences_service,
        )

        await manager.send(endpoint_id, {
            "version": "1.0",
            "type": "room.dashboard",
            "source": "roomhub-core",
            "target": endpoint_id,
            "payload": self.snapshot(
                endpoint.area_id,
                self.maximum_entities_for_firmware(endpoint.firmware_version),
                endpoint_dashboard_preferences_service.excluded_entity_ids(
                    endpoint_id
                ),
            ),
        })

    async def handle_state_changed(self, event: EntityStateChangedEvent) -> None:
        entity = entity_registry.get(event.entity_id)
        if entity is None or entity.area_id is None:
            return
        for endpoint in registry.endpoints.values():
            if endpoint.connected and endpoint.area_id == entity.area_id:
                await self.send(endpoint.device_id)


room_dashboard_service = RoomDashboardService()
