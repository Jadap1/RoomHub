from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json

from .config import PROJECT_NAME, VERSION
from .services.endpoint_service import register_endpoint
from .core.registry import registry


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

            if message["type"] == "register":

                endpoint_id = message["device_id"]

                endpoint = register_endpoint(message)

                await websocket.send_json({
                    "type": "registered",
                    "room": endpoint.room,
                    "server": PROJECT_NAME
                })


    except WebSocketDisconnect:

        if endpoint_id:

            endpoint = registry.get(endpoint_id)

            if endpoint:
                endpoint.connected = False