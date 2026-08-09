from contextlib import closing

from ..core.database import get_connection
from ..core.entity_registry import entity_registry
from ..core.registry import registry
from .room_dashboard_service import SUPPORTED_ENTITY_TYPES, room_dashboard_service


class EndpointDashboardPreferencesService:
    def excluded_entity_ids(self, endpoint_id: str) -> set[str]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                "SELECT entity_id FROM endpoint_entity_exclusions "
                "WHERE endpoint_id = ?",
                (endpoint_id,),
            ).fetchall()
        return {row[0] for row in rows}

    def eligible_entities(self, endpoint_id: str) -> list[dict]:
        endpoint = registry.get(endpoint_id)
        if endpoint is None or endpoint.area_id is None:
            return []
        excluded = self.excluded_entity_ids(endpoint_id)
        entities = [
            {
                "entity_id": entity.entity_id,
                "entity_type": entity.entity_type,
                "name": entity.name,
                "visible": entity.entity_id not in excluded,
            }
            for entity in entity_registry.entities.values()
            if entity.area_id == endpoint.area_id
            and entity.entity_type in SUPPORTED_ENTITY_TYPES
            and entity.entity_category is None
        ]
        return sorted(
            entities,
            key=lambda item: (item["entity_type"], item["name"].casefold()),
        )

    async def replace_exclusions(
        self,
        endpoint_id: str,
        excluded_entity_ids: set[str],
    ) -> dict:
        endpoint = registry.get(endpoint_id)
        if endpoint is None:
            return {"status": "not_found", "endpoint_id": endpoint_id}

        eligible_ids = {
            item["entity_id"] for item in self.eligible_entities(endpoint_id)
        }
        invalid_ids = sorted(excluded_entity_ids - eligible_ids)
        if invalid_ids:
            return {"status": "invalid_entities", "entity_ids": invalid_ids}

        # Preserve choices for other areas so moving a panel away and back
        # restores its previous room-specific dashboard.
        retained_ids = self.excluded_entity_ids(endpoint_id) - eligible_ids
        stored_ids = retained_ids | excluded_entity_ids

        with closing(get_connection()) as connection, connection:
            connection.execute(
                "DELETE FROM endpoint_entity_exclusions WHERE endpoint_id = ?",
                (endpoint_id,),
            )
            connection.executemany(
                "INSERT INTO endpoint_entity_exclusions "
                "(endpoint_id, entity_id) VALUES (?, ?)",
                [(endpoint_id, entity_id) for entity_id in stored_ids],
            )

        await room_dashboard_service.send(endpoint_id)
        return {
            "status": "saved",
            "endpoint_id": endpoint_id,
            "excluded_entity_ids": sorted(excluded_entity_ids),
        }


endpoint_dashboard_preferences_service = EndpointDashboardPreferencesService()
