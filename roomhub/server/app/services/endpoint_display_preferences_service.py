from contextlib import closing

from ..core.database import get_connection
from ..core.registry import registry
from .room_dashboard_service import room_dashboard_service


DEFAULT_PREFERENCES = {
    "tap_to_wake": True,
    "wake_on_voice": True,
    "sleep_timeout_seconds": 0,
    "dashboard_layout": "grouped",
}


class EndpointDisplayPreferencesService:
    def get(self, endpoint_id: str) -> dict:
        with closing(get_connection()) as connection:
            row = connection.execute(
                "SELECT tap_to_wake, wake_on_voice, sleep_timeout_seconds, "
                "dashboard_layout FROM endpoint_display_preferences "
                "WHERE endpoint_id = ?",
                (endpoint_id,),
            ).fetchone()
        if row is None:
            return dict(DEFAULT_PREFERENCES)
        return {
            "tap_to_wake": bool(row[0]),
            "wake_on_voice": bool(row[1]),
            "sleep_timeout_seconds": row[2],
            "dashboard_layout": row[3],
        }

    async def save(
        self,
        endpoint_id: str,
        *,
        tap_to_wake: bool,
        wake_on_voice: bool,
        sleep_timeout_seconds: int,
        dashboard_layout: str,
    ) -> dict:
        if registry.get(endpoint_id) is None:
            return {"status": "not_found", "endpoint_id": endpoint_id}
        with closing(get_connection()) as connection, connection:
            connection.execute(
                "INSERT INTO endpoint_display_preferences "
                "(endpoint_id, tap_to_wake, wake_on_voice, "
                "sleep_timeout_seconds, dashboard_layout) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(endpoint_id) DO UPDATE SET "
                "tap_to_wake=excluded.tap_to_wake, "
                "wake_on_voice=excluded.wake_on_voice, "
                "sleep_timeout_seconds=excluded.sleep_timeout_seconds, "
                "dashboard_layout=excluded.dashboard_layout",
                (
                    endpoint_id,
                    int(tap_to_wake),
                    int(wake_on_voice),
                    sleep_timeout_seconds,
                    dashboard_layout,
                ),
            )
        await room_dashboard_service.send(endpoint_id)
        return {"status": "saved", "endpoint_id": endpoint_id, **self.get(endpoint_id)}


endpoint_display_preferences_service = EndpointDisplayPreferencesService()
