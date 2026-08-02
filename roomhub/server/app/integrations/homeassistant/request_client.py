import asyncio
import json
from typing import Any

from websockets.asyncio.client import ClientConnection


class HomeAssistantRequestError(RuntimeError):
    pass


class HomeAssistantRequestClient:

    def __init__(self) -> None:
        self._websocket: ClientConnection | None = None
        self._next_request_id = 1
        self._pending_requests: dict[
            int,
            asyncio.Future[Any]
        ] = {}

    def attach(
        self,
        websocket: ClientConnection
    ) -> None:
        self._websocket = websocket

    def detach(self) -> None:
        self._websocket = None

    async def send_request(
        self,
        payload: dict[str, Any]
    ) -> Any:

        if self._websocket is None:
            raise RuntimeError(
                "Home Assistant WebSocket is not connected"
            )

        request_id = self._next_request_id
        self._next_request_id += 1

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = (
            loop.create_future()
        )

        self._pending_requests[request_id] = future

        message = {
            "id": request_id,
            **payload
        }

        try:
            await self._websocket.send(
                json.dumps(message)
            )

            return await asyncio.wait_for(
                future,
                timeout=30
            )

        finally:
            self._pending_requests.pop(
                request_id,
                None
            )

    def handle_result(
        self,
        message: dict[str, Any]
    ) -> bool:

        request_id = message.get("id")

        if not isinstance(request_id, int):
            return False

        future = self._pending_requests.get(
            request_id
        )

        if future is None:
            return False

        if future.done():
            return True

        if message.get("success"):

            future.set_result(
                message.get("result")
            )

        else:

            error = message.get("error") or {}

            code = error.get(
                "code",
                "unknown_error"
            )

            text = error.get(
                "message",
                "Home Assistant request failed"
            )

            future.set_exception(
                HomeAssistantRequestError(
                    "Home Assistant request failed: "
                    f"{code} - {text}"
                )
            )

        return True

    def fail_pending_requests(
        self,
        error: BaseException
    ) -> None:

        for future in tuple(
            self._pending_requests.values()
        ):

            if not future.done():
                future.set_exception(error)

        self._pending_requests.clear()
