from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json

from .config import PROJECT_NAME, VERSION
from .services.endpoint_service import register_endpoint
from .core.registry import registry
from .handlers.dispatcher import dispatch

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

            await websocket.send_json(response)


    except WebSocketDisconnect:

        if endpoint_id:

            endpoint = registry.get(endpoint_id)

            if endpoint:
                endpoint.connected = False