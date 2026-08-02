from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json
import asyncio

from .config import PROJECT_NAME, VERSION
from .services.endpoint_service import register_endpoint
from .core.registry import registry
from .handlers.dispatcher import dispatch
from .core.connection_manager import manager
from .core.command_manager import send_command
from .core.command_router import command_router
from .core.state_manager import state_manager
from .core.command_registry import register_commands
from .core.entity_registry_init import register_entities
from .core.entity_registry import entity_registry
from .core.database import initialise_database
from .core.entity_registry import entity_registry
from .core.event_subscriptions import register_event_subscriptions
from .integrations.registry import homeassistant

register_commands()

app = FastAPI(
    title=PROJECT_NAME,
    version=VERSION
)

initialise_database()

entity_registry.load()

register_entities()

register_commands()

register_event_subscriptions()

@app.on_event("startup")
async def start_homeassistant_connector():

    app.state.homeassistant_task = (
        asyncio.create_task(
            homeassistant.start()
        )
    )


@app.on_event("shutdown")
async def stop_homeassistant_connector():

    await homeassistant.stop()

    task = getattr(
        app.state,
        "homeassistant_task",
        None
    )

    if task:

        task.cancel()

@app.get("/entities")
async def entities():

    return entity_registry.get_all()

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
        "entities": len(
            entity_registry.entities
        ),
        "homeassistant": {
            "connected": (
                homeassistant.connected
            )
        }
    }

@app.get("/endpoints")
async def endpoints():
    return registry.get_all()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):

    await websocket.accept()

    endpoint_id = None

    try:
        while True:

            data = await websocket.receive_text()

            message = json.loads(data)

            if message["type"] == "endpoint.register":

                endpoint_id = message["payload"]["device_id"]

                await manager.connect(
                    endpoint_id,
                    websocket
                )


            response = await dispatch(message)

            await websocket.send_json(response)


    except WebSocketDisconnect:

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
            "payload": {
                "screen": "home"
            }
        }
    )

    return {
        "status": "sent",
        "target": endpoint_id
    }

@app.post("/test/light/{endpoint_id}")
async def test_light(endpoint_id: str):

    message = {
        "version": "1.0",
        "type": "light.toggle",
        "source": "roomhub-core",
        "target": endpoint_id,
        "payload": {
            "entity_id": "test_light"
        }
    }

    response = await command_router.execute(message)

    return response

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
        return {
            "error": "not found"
        }

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

    from .core.command_router import command_router

    return await command_router.execute(message)
