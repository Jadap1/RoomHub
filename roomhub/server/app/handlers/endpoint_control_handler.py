from ..services.endpoint_control_service import endpoint_control_service


async def handle_endpoint_control_status(message: dict) -> dict:
    return endpoint_control_service.update(
        message.get("source"), message.get("payload") or {}
    )
