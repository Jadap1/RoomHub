from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json

from .config import PROJECT_NAME, VERSION
from .services.endpoint_service import register_endpoint
from .core.registry import registry
from .handlers.dispatcher import dispatch
from .core.connection_manager import manager
from .core.command_manager import send_command
from .core.state_manager import state_manager

app = FastAPI(
    title=PROJECT_NAME,
    version=VERSION
)


@app.get("/")
async def root():
    return {
        "project": PROJECT_NAME,
        "version": VERSION,
        "status": "online"
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

            response = await dispatch(message)

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
@app.get("/state/{endpoint_id}")
async def endpoint_state(endpoint_id: str):

    endpoint = registry.get(endpoint_id)

    if not endpoint:
        return None

    return endpoint.state