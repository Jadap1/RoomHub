import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .config import PROJECT_NAME, VERSION
from .core import database
from .core.area_registry import area_registry
from .core.command_registry import register_commands
from .core.command_router import command_router
from .core.connection_manager import manager
from .core.device_registry import device_registry
from .core.entity_registry import entity_registry
from .core.entity_registry_init import register_entities
from .core.event_subscriptions import register_event_subscriptions
from .core.floor_registry import floor_registry
from .core.registry import registry
from .handlers.dispatcher import dispatch
from .integrations.registry import homeassistant
from .services.voice_audio_service import VoiceAudioConnection
from .services.audio_command_service import (
    AudioPlayRequest,
    audio_command_service,
)
from .services.endpoint_assignment_service import endpoint_assignment_service
from .services.notification_service import NotificationRequest, notification_service


def create_app(
    database_path: str | Path | None = None,
    homeassistant_connector=None
) -> FastAPI:

    connector = (
        homeassistant_connector
        if homeassistant_connector is not None
        else homeassistant
    )

    if database_path is not None:
        database.DATABASE = Path(database_path)

    database.initialise_database()
    entity_registry.load()
    floor_registry.load()
    area_registry.load()
    device_registry.load()
    register_entities()
    register_commands()
    register_event_subscriptions(connector)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.homeassistant_task = asyncio.create_task(
            connector.start()
        )
        try:
            yield
        finally:
            await connector.stop()
            task = getattr(
                app.state,
                "homeassistant_task",
                None
            )
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(
        title=PROJECT_NAME,
        version=VERSION,
        lifespan=lifespan
    )

    @app.get("/entities")
    async def entities():
        return entity_registry.get_all()

    @app.get("/floors")
    async def floors():
        return floor_registry.get_all()

    @app.get("/areas")
    async def areas():
        return area_registry.get_all()

    @app.get("/devices")
    async def devices():
        return device_registry.get_all()

    @app.get("/floors/{floor_id}")
    async def floor(floor_id: str):
        item = floor_registry.get(floor_id)
        if not item:
            return {"error": "not found"}
        return item.model_dump()

    @app.get("/areas/{area_id}")
    async def area(area_id: str):
        item = area_registry.get(area_id)
        if not item:
            return {"error": "not found"}
        return item.model_dump()

    @app.get("/devices/{device_id}")
    async def device(device_id: str):
        item = device_registry.get(device_id)
        if not item:
            return {"error": "not found"}
        return item.model_dump()

    @app.get("/")
    async def root():
        return {
            "project": PROJECT_NAME,
            "version": VERSION,
            "status": "online"
        }

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": PROJECT_NAME,
            "version": VERSION,
            "entities": len(entity_registry.entities),
            "homeassistant": {
                "connected": connector.connected
            }
        }

    @app.get("/endpoints")
    async def endpoints():
        return registry.get_all()

    @app.put("/endpoints/{endpoint_id}/area/{area_id}")
    async def assign_endpoint_area(endpoint_id: str, area_id: str):
        return endpoint_assignment_service.assign(endpoint_id, area_id)

    @app.post("/notifications")
    async def create_notification(request: NotificationRequest):
        return await notification_service.notify(request)

    @app.get("/notifications/{delivery_id}")
    async def notification_delivery(delivery_id: str):
        delivery = notification_service.get(delivery_id)
        return delivery if delivery is not None else {"error": "not found"}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        endpoint_id = None
        audio = VoiceAudioConnection()
        try:
            while True:
                event = await websocket.receive()
                if event["type"] == "websocket.disconnect":
                    break

                binary = event.get("bytes")
                if binary is not None:
                    response = await audio.send_audio(binary)
                    if response is not None:
                        await websocket.send_json(response)
                    continue

                data = event.get("text")
                if data is None:
                    continue
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "version": "1.0",
                        "type": "error",
                        "payload": {"message": "Invalid JSON"},
                    })
                    continue

                message_type = message.get("type")
                if message_type == "endpoint.register":
                    endpoint_id = message["payload"]["device_id"]
                    await manager.connect(
                        endpoint_id,
                        websocket
                    )
                    response = await dispatch(message)
                elif (
                    isinstance(message_type, str)
                    and message_type.startswith("voice.audio.")
                ):
                    if endpoint_id is None:
                        response = {
                            "version": "1.0",
                            "type": "voice.audio.rejected",
                            "payload": {
                                "status": "rejected",
                                "reason": "endpoint_not_registered",
                            },
                        }
                    elif message.get("source") not in (None, endpoint_id):
                        response = {
                            "version": "1.0",
                            "type": "voice.audio.rejected",
                            "payload": {
                                "status": "rejected",
                                "reason": "source_mismatch",
                            },
                        }
                    elif message_type == "voice.audio.start":
                        response = await audio.start(
                            message.get("payload") or {}
                        )
                    elif message_type == "voice.audio.end":
                        response = await audio.finish(endpoint_id)
                    elif message_type == "voice.audio.cancel":
                        response = await audio.cancel()
                    else:
                        response = {
                            "version": "1.0",
                            "type": "voice.audio.rejected",
                            "payload": {
                                "status": "rejected",
                                "reason": "unknown_audio_message",
                            },
                        }
                else:
                    response = await dispatch(message)
                await websocket.send_json(response)
        except WebSocketDisconnect:
            pass
        finally:
            await audio.close()
            if endpoint_id:
                endpoint = registry.get(endpoint_id)
                if endpoint:
                    endpoint.connected = False
                manager.disconnect(endpoint_id)

    @app.post("/test/display/{endpoint_id}")
    async def test_display(endpoint_id: str):
        await manager.send(
            endpoint_id,
            {
                "version": "1.0",
                "type": "display.show",
                "source": "roomhub-core",
                "target": endpoint_id,
                "payload": {"screen": "home"}
            }
        )
        return {
            "status": "sent",
            "target": endpoint_id
        }

    @app.post("/audio/{endpoint_id}/play")
    async def play_audio(endpoint_id: str, request: AudioPlayRequest):
        return await audio_command_service.play(endpoint_id, request)

    @app.post("/audio/{endpoint_id}/stop/{request_id}")
    async def stop_audio(endpoint_id: str, request_id: str):
        return await audio_command_service.stop(endpoint_id, request_id)

    @app.post("/test/light/{endpoint_id}")
    async def test_light(endpoint_id: str):
        message = {
            "version": "1.0",
            "type": "light.toggle",
            "source": "roomhub-core",
            "target": endpoint_id,
            "payload": {"entity_id": "test_light"}
        }
        return await command_router.execute(message)

    @app.get("/state/{endpoint_id}")
    async def endpoint_state(endpoint_id: str):
        endpoint = registry.get(endpoint_id)
        if not endpoint:
            return None
        return endpoint.state

    @app.get("/entities/{entity_id}")
    async def entity(entity_id: str):
        item = entity_registry.get(entity_id)
        if not item:
            return {"error": "not found"}
        return item.model_dump()

    @app.post("/test/command/light")
    async def test_light_command():
        message = {
            "version": "1.0",
            "type": "light.toggle",
            "source": "test",
            "target": "roomhub-core",
            "payload": {
                "entity_id": "light.kitchen_main"
            }
        }
        return await command_router.execute(message)

    return app
