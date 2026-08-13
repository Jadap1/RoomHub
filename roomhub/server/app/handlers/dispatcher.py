from .endpoint_handler import handle_endpoint_register
from .heartbeat_handler import handle_heartbeat
from .input_handler import handle_input
from .voice_handler import handle_voice_transcript
from ..core.command_router import command_router
from .audio_handler import handle_audio_status
from .dashboard_handler import handle_dashboard_activate
from .firmware_handler import handle_firmware_status
from ..services.notification_service import notification_service


async def dispatch(message):

    message_type = message.get("type")


    if message_type == "endpoint.register":

        return await handle_endpoint_register(message)


    elif message_type == "endpoint.heartbeat":

        return await handle_heartbeat(message)

    elif message_type == "input.button":

        return await handle_input(message)

    elif message_type == "voice.transcript":

        return await handle_voice_transcript(message)

    elif message_type == "audio.status":

        return await handle_audio_status(message)

    elif message_type == "dashboard.activate":

        return await handle_dashboard_activate(message)

    elif message_type == "firmware.status":

        return await handle_firmware_status(message)

    elif message_type == "notification.dismissed":

        payload = message.get("payload", {})
        notification_service.update_status(
            payload.get("delivery_id"), message.get("source"), "dismissed"
        )
        return {"status": "dismissed"}

    elif message_type in command_router.commands:

        return await command_router.execute(message)


    return {
        "version": "1.0",
        "type": "error",
        "payload": {
            "message": f"Unknown message type: {message_type}"
        }
    }
