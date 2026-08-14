import asyncio
from typing import Dict
from fastapi import WebSocket


class ConnectionManager:

    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}
        self._send_locks: Dict[str, asyncio.Lock] = {}


    async def connect(
        self,
        endpoint_id: str,
        websocket: WebSocket
    ):

        self.connections[endpoint_id] = websocket
        self._send_locks[endpoint_id] = asyncio.Lock()


    def disconnect(
        self,
        endpoint_id: str,
        websocket: WebSocket | None = None,
    ) -> bool:

        current = self.connections.get(endpoint_id)
        if current is not None and (websocket is None or current is websocket):
            del self.connections[endpoint_id]
            self._send_locks.pop(endpoint_id, None)
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
            lock = self._send_locks.setdefault(endpoint_id, asyncio.Lock())
            async with lock:
                await websocket.send_json(message)
            return True
        except Exception:
            self.disconnect(endpoint_id, websocket)
            return False

    async def send_bytes(
        self,
        endpoint_id: str,
        data: bytes,
    ) -> bool:
        websocket = self.get(endpoint_id)
        if not websocket:
            return False
        try:
            lock = self._send_locks.setdefault(endpoint_id, asyncio.Lock())
            async with lock:
                await websocket.send_bytes(data)
            return True
        except Exception:
            self.disconnect(endpoint_id, websocket)
            return False

manager = ConnectionManager()
