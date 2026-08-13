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
        endpoint_id: str,
        websocket: WebSocket | None = None,
    ) -> bool:

        current = self.connections.get(endpoint_id)
        if current is not None and (websocket is None or current is websocket):
            del self.connections[endpoint_id]
            return True
        return False


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

        if not websocket:
            return False
        try:
            await websocket.send_json(message)
            return True
        except Exception:
            self.disconnect(endpoint_id, websocket)
            return False


manager = ConnectionManager()
