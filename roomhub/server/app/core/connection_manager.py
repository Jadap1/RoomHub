from typing import Dict
from fastapi import WebSocket


class ConnectionManager:

    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}


    async def connect(
        self,
        endpoint_id: str,
        websocket: WebSocket
    ):

        self.connections[endpoint_id] = websocket


    def disconnect(
        self,
        endpoint_id: str
    ):

        if endpoint_id in self.connections:
            del self.connections[endpoint_id]


    def get(
        self,
        endpoint_id: str
    ):

        return self.connections.get(endpoint_id)


    async def send(
        self,
        endpoint_id: str,
        message: dict
    ):

        websocket = self.get(endpoint_id)

        if websocket:
            await websocket.send_json(message)


manager = ConnectionManager()