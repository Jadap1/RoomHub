from ..services.firmware_deployment_service import firmware_deployment_service


async def handle_firmware_status(message: dict) -> dict:
    endpoint_id = message.get("source")
    result = firmware_deployment_service.update(
        endpoint_id if isinstance(endpoint_id, str) else "",
        message.get("payload") or {},
    )
    return {"version": "1.0", "type": "firmware.status.ack", "payload": result}
