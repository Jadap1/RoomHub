from ..core.area_registry import area_registry
from ..core.connection_manager import manager
from ..core.entity_registry import entity_registry
from ..core.registry import registry
from ..events.entity_events import EntityStateChangedEvent


SUPPORTED_ENTITY_TYPES = {"light", "switch", "climate"}


class RoomDashboardService:
    def snapshot(self, area_id: str | None) -> dict:
        area = area_registry.get(area_id) if area_id else None
        entities = []
        if area is not None:
            for entity in entity_registry.entities.values():
                if (
                    entity.area_id != area_id
                    or entity.entity_type not in SUPPORTED_ENTITY_TYPES
                    or entity.entity_category is not None
                ):
                    continue
                entities.append({
                    "entity_id": entity.entity_id,
                    "entity_type": entity.entity_type,
                    "name": entity.name,
                    "state": entity_registry.get_state(entity.entity_id),
                })
        entities.sort(key=lambda item: (item["entity_type"], item["name"].casefold()))
        return {
            "area_id": area_id,
            "area_name": area.name if area is not None else "Unassigned",
            "entities": entities,
        }

    async def send(self, endpoint_id: str) -> None:
        endpoint = registry.get(endpoint_id)
        if endpoint is None or not endpoint.connected:
            return
        await manager.send(endpoint_id, {
            "version": "1.0",
            "type": "room.dashboard",
            "source": "roomhub-core",
            "target": endpoint_id,
            "payload": self.snapshot(endpoint.area_id),
        })

    async def handle_state_changed(self, event: EntityStateChangedEvent) -> None:
        entity = entity_registry.get(event.entity_id)
        if entity is None or entity.area_id is None:
            return
        for endpoint in registry.endpoints.values():
            if endpoint.connected and endpoint.area_id == entity.area_id:
                await self.send(endpoint.device_id)


room_dashboard_service = RoomDashboardService()
