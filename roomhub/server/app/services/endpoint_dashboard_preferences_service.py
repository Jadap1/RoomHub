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

    def entity_preferences(self, endpoint_id: str) -> dict[str, dict]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                "SELECT entity_id, position, pinned "
                "FROM endpoint_entity_preferences WHERE endpoint_id = ?",
                (endpoint_id,),
            ).fetchall()
        return {
            row[0]: {"position": row[1], "pinned": bool(row[2])}
            for row in rows
        }

    def eligible_entities(self, endpoint_id: str) -> list[dict]:
        endpoint = registry.get(endpoint_id)
        if endpoint is None or endpoint.area_id is None:
            return []
        excluded = self.excluded_entity_ids(endpoint_id)
        preferences = self.entity_preferences(endpoint_id)
        entities = [
            {
                "entity_id": entity.entity_id,
                "entity_type": entity.entity_type,
                "name": entity.name,
                "visible": entity.entity_id not in excluded,
                "pinned": preferences.get(entity.entity_id, {}).get(
                    "pinned", False
                ),
            }
            for entity in entity_registry.entities.values()
            if entity.area_id == endpoint.area_id
            and entity.entity_type in SUPPORTED_ENTITY_TYPES
            and entity.entity_category is None
        ]
        default_position = len(preferences)
        return sorted(entities, key=lambda item: (
            not item["pinned"],
            preferences.get(item["entity_id"], {}).get(
                "position", default_position
            ),
            item["entity_type"],
            item["name"].casefold(),
        ))

    async def replace_exclusions(
        self,
        endpoint_id: str,
        excluded_entity_ids: set[str],
        entity_order: list[str] | None = None,
        pinned_entity_ids: set[str] | None = None,
    ) -> dict:
        endpoint = registry.get(endpoint_id)
        if endpoint is None:
            return {"status": "not_found", "endpoint_id": endpoint_id}

        eligible_ids = {
            item["entity_id"] for item in self.eligible_entities(endpoint_id)
        }
        entity_order = entity_order or [
            item["entity_id"] for item in self.eligible_entities(endpoint_id)
        ]
        pinned_entity_ids = pinned_entity_ids or set()
        invalid_ids = sorted(excluded_entity_ids - eligible_ids)
        invalid_order = sorted(set(entity_order) ^ eligible_ids)
        invalid_pins = sorted(pinned_entity_ids - eligible_ids)
        duplicate_order = len(entity_order) != len(set(entity_order))
        if invalid_ids or invalid_order or invalid_pins or duplicate_order:
            return {
                "status": "invalid_entities",
                "entity_ids": sorted(
                    set(invalid_ids + invalid_order + invalid_pins)
                ),
            }

        # Preserve choices for other areas so moving a panel away and back
        # restores its previous room-specific dashboard.
        retained_ids = self.excluded_entity_ids(endpoint_id) - eligible_ids
        stored_ids = retained_ids | excluded_entity_ids
        existing_preferences = self.entity_preferences(endpoint_id)
        retained_preferences = {
            entity_id: preference
            for entity_id, preference in existing_preferences.items()
            if entity_id not in eligible_ids
        }

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
            connection.execute(
                "DELETE FROM endpoint_entity_preferences WHERE endpoint_id = ?",
                (endpoint_id,),
            )
            preference_rows = [
                (endpoint_id, entity_id, preference["position"], preference["pinned"])
                for entity_id, preference in retained_preferences.items()
            ] + [
                (endpoint_id, entity_id, position, entity_id in pinned_entity_ids)
                for position, entity_id in enumerate(entity_order)
            ]
            connection.executemany(
                "INSERT INTO endpoint_entity_preferences "
                "(endpoint_id, entity_id, position, pinned) VALUES (?, ?, ?, ?)",
                preference_rows,
            )

        await room_dashboard_service.send(endpoint_id)
        return {
            "status": "saved",
            "endpoint_id": endpoint_id,
            "excluded_entity_ids": sorted(excluded_entity_ids),
            "entity_order": entity_order,
            "pinned_entity_ids": sorted(pinned_entity_ids),
        }


endpoint_dashboard_preferences_service = EndpointDashboardPreferencesService()
