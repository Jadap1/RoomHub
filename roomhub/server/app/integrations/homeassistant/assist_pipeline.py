import asyncio
import json
from collections.abc import Callable
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from ...integrations.homeassistant_auth import (
    get_homeassistant_assist_pipeline_name,
    get_homeassistant_connection_settings,
)
from .authentication import authenticate
from .request_client import HomeAssistantRequestError


class HomeAssistantAssistError(RuntimeError):
    pass


ConnectWebSocket = Callable[..., Any]


class HomeAssistantSpeechToTextSession:
    def __init__(
        self,
        sample_rate: int = 16000,
        pipeline_name: str | None = None,
        connect_websocket: ConnectWebSocket = websockets.connect,
    ) -> None:
        self.sample_rate = sample_rate
        self.pipeline_name = (
            pipeline_name
            or get_homeassistant_assist_pipeline_name()
        )
        self._connect_websocket = connect_websocket
        self._websocket: ClientConnection | None = None
        self._binary_handler_id: int | None = None
        self._run_request_id = 2
        self._started = False

    async def start(self) -> None:
        if self._websocket is not None:
            raise RuntimeError("Speech-to-text session already started")

        settings = get_homeassistant_connection_settings()
        websocket = await self._connect_websocket(
            settings.websocket_url,
            open_timeout=20,
            ping_interval=30,
            ping_timeout=20,
            max_size=16 * 1024 * 1024,
        )
        self._websocket = websocket

        try:
            await authenticate(
                websocket,
                settings.access_token,
            )
            pipelines = await self._request(
                1,
                {"type": "assist_pipeline/pipeline/list"},
            )
            pipeline_id = self._find_pipeline_id(pipelines)

            await websocket.send(json.dumps({
                "id": self._run_request_id,
                "type": "assist_pipeline/run",
                "start_stage": "stt",
                "end_stage": "stt",
                "pipeline": pipeline_id,
                "input": {
                    "sample_rate": self.sample_rate,
                },
            }))
            await self._wait_until_ready()
            self._started = True
        except Exception:
            await self.abort()
            raise

    def _find_pipeline_id(self, result: Any) -> str:
        pipelines = (
            result.get("pipelines", [])
            if isinstance(result, dict)
            else []
        )
        matches = [
            pipeline
            for pipeline in pipelines
            if pipeline.get("name") == self.pipeline_name
        ]
        if len(matches) != 1:
            raise HomeAssistantAssistError(
                "Expected exactly one Home Assistant Assist "
                f"pipeline named '{self.pipeline_name}', "
                f"found {len(matches)}"
            )
        pipeline_id = matches[0].get("id")
        if not isinstance(pipeline_id, str):
            raise HomeAssistantAssistError(
                "Home Assistant Assist pipeline has no valid id"
            )
        return pipeline_id

    async def _request(
        self,
        request_id: int,
        payload: dict[str, Any],
    ) -> Any:
        websocket = self._require_websocket()
        await websocket.send(json.dumps({
            "id": request_id,
            **payload,
        }))
        while True:
            message = await self._receive_json()
            if (
                message.get("type") == "result"
                and message.get("id") == request_id
            ):
                if not message.get("success"):
                    error = message.get("error") or {}
                    raise HomeAssistantRequestError(
                        "Home Assistant request failed: "
                        f"{error.get('code', 'unknown_error')} - "
                        f"{error.get('message', 'request failed')}"
                    )
                return message.get("result")

    async def _wait_until_ready(self) -> None:
        result_received = False
        stt_started = False

        async with asyncio.timeout(30):
            while not (
                result_received
                and stt_started
                and self._binary_handler_id is not None
            ):
                message = await self._receive_json()
                if message.get("id") != self._run_request_id:
                    continue
                if message.get("type") == "result":
                    if not message.get("success"):
                        error = message.get("error") or {}
                        raise HomeAssistantAssistError(
                            "Unable to start Home Assistant STT: "
                            f"{error.get('message', 'unknown error')}"
                        )
                    result_received = True
                    continue
                if message.get("type") != "event":
                    continue
                event = message.get("event") or {}
                event_type = event.get("type")
                event_data = event.get("data") or {}
                if event_type == "run-start":
                    handler_id = (
                        event_data.get("runner_data") or {}
                    ).get("stt_binary_handler_id")
                    if not isinstance(handler_id, int):
                        raise HomeAssistantAssistError(
                            "Home Assistant did not provide an STT "
                            "binary handler"
                        )
                    if not 0 <= handler_id <= 255:
                        raise HomeAssistantAssistError(
                            "Home Assistant STT binary handler is invalid"
                        )
                    self._binary_handler_id = handler_id
                elif event_type == "stt-start":
                    stt_started = True
                elif event_type == "error":
                    raise self._event_error(event_data)
                elif event_type == "run-end":
                    raise HomeAssistantAssistError(
                        "Home Assistant STT ended before accepting audio"
                    )

    async def send_audio(self, audio: bytes) -> None:
        if not self._started or self._binary_handler_id is None:
            raise RuntimeError("Speech-to-text session is not ready")
        if not audio:
            raise ValueError("Audio frame must not be empty")
        if len(audio) % 2:
            raise ValueError(
                "16-bit PCM audio frames must have an even byte length"
            )
        if len(audio) > 64 * 1024:
            raise ValueError("Audio frame exceeds 64 KiB")
        await self._require_websocket().send(
            bytes([self._binary_handler_id]) + audio
        )

    async def finish(self) -> str:
        if not self._started or self._binary_handler_id is None:
            raise RuntimeError("Speech-to-text session is not ready")

        websocket = self._require_websocket()
        await websocket.send(bytes([self._binary_handler_id]))
        transcript = None

        try:
            async with asyncio.timeout(60):
                while True:
                    message = await self._receive_json()
                    if message.get("id") != self._run_request_id:
                        continue
                    if message.get("type") != "event":
                        continue
                    event = message.get("event") or {}
                    event_type = event.get("type")
                    event_data = event.get("data") or {}
                    if event_type == "stt-end":
                        text = (
                            event_data.get("stt_output") or {}
                        ).get("text")
                        if isinstance(text, str) and text.strip():
                            transcript = text.strip()
                    elif event_type == "error":
                        raise self._event_error(event_data)
                    elif event_type == "run-end":
                        if transcript is None:
                            raise HomeAssistantAssistError(
                                "Home Assistant STT returned no transcript"
                            )
                        return transcript
        finally:
            await self._close()

    async def abort(self) -> None:
        await self._close()

    async def _close(self) -> None:
        websocket = self._websocket
        self._websocket = None
        self._binary_handler_id = None
        self._started = False
        if websocket is not None:
            await websocket.close()

    async def _receive_json(self) -> dict[str, Any]:
        raw_message = await self._require_websocket().recv()
        if not isinstance(raw_message, str):
            raise HomeAssistantAssistError(
                "Unexpected binary message from Home Assistant"
            )
        message = json.loads(raw_message)
        if not isinstance(message, dict):
            raise HomeAssistantAssistError(
                "Unexpected Home Assistant message"
            )
        return message

    def _require_websocket(self) -> ClientConnection:
        if self._websocket is None:
            raise RuntimeError(
                "Home Assistant speech WebSocket is not connected"
            )
        return self._websocket

    @staticmethod
    def _event_error(data: dict[str, Any]) -> HomeAssistantAssistError:
        return HomeAssistantAssistError(
            "Home Assistant Assist pipeline failed: "
            f"{data.get('code', 'unknown_error')} - "
            f"{data.get('message', 'pipeline failed')}"
        )
