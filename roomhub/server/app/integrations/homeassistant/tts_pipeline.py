import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import websockets
from websockets.asyncio.client import ClientConnection

from ...integrations.homeassistant_auth import (
    get_homeassistant_assist_pipeline_name,
    get_homeassistant_connection_settings,
    get_homeassistant_public_url,
)
from .authentication import authenticate


class HomeAssistantTextToSpeechError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpeechOutput:
    url: str
    mime_type: str
    token: str | None = None


ConnectWebSocket = Callable[..., Any]


class HomeAssistantTextToSpeechClient:
    def __init__(
        self,
        pipeline_name: str | None = None,
        connect_websocket: ConnectWebSocket = websockets.connect,
    ) -> None:
        self.pipeline_name = (
            pipeline_name
            or get_homeassistant_assist_pipeline_name()
        )
        self._connect_websocket = connect_websocket

    async def synthesize(self, text: str) -> SpeechOutput:
        text = text.strip()
        if not text:
            raise ValueError("Text-to-speech input must not be empty")

        settings = get_homeassistant_connection_settings()
        public_url = get_homeassistant_public_url()
        websocket = await self._connect_websocket(
            settings.websocket_url,
            open_timeout=20,
            ping_interval=30,
            ping_timeout=20,
            max_size=16 * 1024 * 1024,
        )

        try:
            await authenticate(websocket, settings.access_token)
            pipelines = await self._request(
                websocket,
                1,
                {"type": "assist_pipeline/pipeline/list"},
            )
            pipeline_id = self._find_pipeline_id(pipelines)
            await websocket.send(json.dumps({
                "id": 2,
                "type": "assist_pipeline/run",
                "start_stage": "tts",
                "end_stage": "tts",
                "pipeline": pipeline_id,
                "input": {"text": text},
            }))
            return await self._wait_for_output(websocket, public_url)
        finally:
            await websocket.close()

    async def _request(
        self,
        websocket: ClientConnection,
        request_id: int,
        payload: dict[str, Any],
    ) -> Any:
        await websocket.send(json.dumps({"id": request_id, **payload}))
        async with asyncio.timeout(30):
            while True:
                message = await self._receive_json(websocket)
                if (
                    message.get("type") == "result"
                    and message.get("id") == request_id
                ):
                    if not message.get("success"):
                        raise self._result_error(message)
                    return message.get("result")

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
            raise HomeAssistantTextToSpeechError(
                "Expected exactly one Home Assistant Assist "
                f"pipeline named '{self.pipeline_name}', "
                f"found {len(matches)}"
            )
        pipeline_id = matches[0].get("id")
        if not isinstance(pipeline_id, str):
            raise HomeAssistantTextToSpeechError(
                "Home Assistant Assist pipeline has no valid id"
            )
        return pipeline_id

    async def _wait_for_output(
        self,
        websocket: ClientConnection,
        public_url: str,
    ) -> SpeechOutput:
        run_accepted = False
        output = None

        async with asyncio.timeout(60):
            while True:
                message = await self._receive_json(websocket)
                if message.get("id") != 2:
                    continue
                if message.get("type") == "result":
                    if not message.get("success"):
                        raise self._result_error(message)
                    run_accepted = True
                    continue
                if message.get("type") != "event":
                    continue

                event = message.get("event") or {}
                event_type = event.get("type")
                data = event.get("data") or {}
                if event_type == "tts-end":
                    output = self._parse_output(data, public_url)
                elif event_type == "error":
                    raise HomeAssistantTextToSpeechError(
                        "Home Assistant TTS failed: "
                        f"{data.get('code', 'unknown_error')} - "
                        f"{data.get('message', 'synthesis failed')}"
                    )
                elif event_type == "run-end":
                    if not run_accepted:
                        raise HomeAssistantTextToSpeechError(
                            "Home Assistant ended TTS before accepting the run"
                        )
                    if output is None:
                        raise HomeAssistantTextToSpeechError(
                            "Home Assistant TTS returned no audio"
                        )
                    return output

    @staticmethod
    def _parse_output(
        data: dict[str, Any],
        public_url: str,
    ) -> SpeechOutput:
        nested_output = data.get("tts_output")
        output = (
            nested_output
            if isinstance(nested_output, dict)
            else data
        )
        url = output.get("url")
        mime_type = output.get("mime_type")
        token = output.get("token")
        if not isinstance(url, str) or not url:
            raise HomeAssistantTextToSpeechError(
                "Home Assistant TTS returned no audio URL"
            )
        if not isinstance(mime_type, str) or not mime_type:
            raise HomeAssistantTextToSpeechError(
                "Home Assistant TTS returned no media type"
            )
        return SpeechOutput(
            url=urljoin(f"{public_url.rstrip('/')}/", url),
            mime_type=mime_type,
            token=token if isinstance(token, str) else None,
        )

    @staticmethod
    async def _receive_json(
        websocket: ClientConnection,
    ) -> dict[str, Any]:
        raw_message = await websocket.recv()
        if not isinstance(raw_message, str):
            raise HomeAssistantTextToSpeechError(
                "Unexpected binary message from Home Assistant"
            )
        message = json.loads(raw_message)
        if not isinstance(message, dict):
            raise HomeAssistantTextToSpeechError(
                "Unexpected Home Assistant message"
            )
        return message

    @staticmethod
    def _result_error(
        message: dict[str, Any],
    ) -> HomeAssistantTextToSpeechError:
        error = message.get("error") or {}
        return HomeAssistantTextToSpeechError(
            "Home Assistant TTS request failed: "
            f"{error.get('code', 'unknown_error')} - "
            f"{error.get('message', 'request failed')}"
        )
