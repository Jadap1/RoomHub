from contextlib import closing

from ..core.area_registry import area_registry
from ..core.database import get_connection
from ..core.registry import registry
from .room_dashboard_service import room_dashboard_service


class EndpointAssignmentService:
    def get_area_id(self, endpoint_id: str) -> str | None:
        with closing(get_connection()) as connection:
            row = connection.execute(
                "SELECT area_id FROM endpoint_assignments WHERE endpoint_id = ?",
                (endpoint_id,),
            ).fetchone()
        return None if row is None else row[0]

    def apply(self, endpoint) -> None:
        area_id = self.get_area_id(endpoint.device_id)
        if area_id is None:
            reported_area_id = endpoint.area_id
            if reported_area_id is None or area_registry.get(reported_area_id) is None:
                return
            area_id = reported_area_id
            with closing(get_connection()) as connection, connection:
                connection.execute(
                    "INSERT INTO endpoint_assignments (endpoint_id, area_id) VALUES (?, ?)",
                    (endpoint.device_id, area_id),
                )
        endpoint.area_id = area_id
        area = area_registry.get(area_id)
        endpoint.room = area.name if area is not None else area_id

    async def assign(self, endpoint_id: str, area_id: str) -> dict:
        endpoint = registry.get(endpoint_id)
        if endpoint is None:
            return {"status": "not_found", "endpoint_id": endpoint_id}
        area = area_registry.get(area_id)
        if area is None:
            return {"status": "invalid_area", "area_id": area_id}
        with closing(get_connection()) as connection, connection:
            connection.execute(
                """
                INSERT INTO endpoint_assignments (endpoint_id, area_id)
                VALUES (?, ?)
                ON CONFLICT(endpoint_id) DO UPDATE SET area_id = excluded.area_id
                """,
                (endpoint_id, area_id),
            )
        endpoint.area_id = area_id
        endpoint.room = area.name
        await room_dashboard_service.send(endpoint_id)
        return {
            "status": "assigned",
            "endpoint_id": endpoint_id,
            "area_id": area_id,
            "room": area.name,
        }


endpoint_assignment_service = EndpointAssignmentService()
