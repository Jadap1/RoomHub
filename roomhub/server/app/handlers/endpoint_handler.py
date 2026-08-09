from ..services.endpoint_service import register_endpoint
from ..services.room_dashboard_service import room_dashboard_service
from ..services.endpoint_dashboard_preferences_service import (
    endpoint_dashboard_preferences_service,
)


async def handle_endpoint_register(message):

    endpoint = register_endpoint(
        message["payload"]
    )

    return {
        "version": "1.0",
        "type": "endpoint.registered",
        "payload": {
            "device_id": endpoint.device_id,
            "room": endpoint.room,
            "dashboard": room_dashboard_service.snapshot(
                endpoint.area_id,
                room_dashboard_service.maximum_entities_for_firmware(
                    endpoint.firmware_version
                ),
                endpoint_dashboard_preferences_service.excluded_entity_ids(
                    endpoint.device_id
                ),
                endpoint_dashboard_preferences_service.entity_preferences(
                    endpoint.device_id
                ),
            ),
        }
    }
