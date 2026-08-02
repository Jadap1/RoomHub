import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.app_factory import create_app
from app.core import database
from app.core.area_registry import area_registry
from app.core.device_registry import device_registry
from app.core.entity_registry import entity_registry
from app.events.entity_events import (
    AreaDiscoveredEvent,
    DeviceDiscoveredEvent,
)


class FakeConnector:
    def __init__(self):
        self.connected = False
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    async def start(self):
        self.connected = True
        self.started.set()
        await self.stopped.wait()

    async def stop(self):
        self.connected = False
        self.stopped.set()

    async def handle_entity_command(self, event):
        return None


class FakeVoiceAudioConnection:
    instances = []

    def __init__(self):
        self.frames = []
        self.finished_for = None
        self.closed = False
        self.__class__.instances.append(self)

    async def start(self, payload):
        return {
            "version": "1.0",
            "type": "voice.audio.ready",
            "payload": payload,
        }

    async def send_audio(self, audio):
        self.frames.append(audio)
        return None

    async def finish(self, endpoint_id):
        self.finished_for = endpoint_id
        return {
            "version": "1.0",
            "type": "voice.intent.accepted",
            "payload": {"status": "accepted"},
        }

    async def cancel(self):
        return {
            "version": "1.0",
            "type": "voice.audio.cancelled",
            "payload": {"status": "cancelled"},
        }

    async def close(self):
        self.closed = True


async def get_json(app, path):
    sent = []
    received = False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {
                "type": "http.request",
                "body": b"",
                "more_body": False
            }
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("test", 1),
            "server": ("test", 80)
        },
        receive,
        send
    )

    start = next(
        message
        for message in sent
        if message["type"] == "http.response.start"
    )
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return start["status"], json.loads(body)


class AppFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_routes_and_lifecycle_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "roomhub.db"
            connector = FakeConnector()

            with patch.object(
                database,
                "DATABASE",
                database_path
            ):
                app = create_app(
                    database_path=database_path,
                    homeassistant_connector=connector
                )

                self.assertEqual(
                    entity_registry.get(
                        "light.kitchen_main"
                    ).integration,
                    "roomhub"
                )

                await area_registry.handle_discovered(
                    AreaDiscoveredEvent(
                        area_id="kitchen",
                        name="Kitchen"
                    )
                )
                await device_registry.handle_discovered(
                    DeviceDiscoveredEvent(
                        device_id="device-1",
                        name="Lamp",
                        area_id="kitchen"
                    )
                )

                async with app.router.lifespan_context(app):
                    await asyncio.wait_for(
                        connector.started.wait(),
                        timeout=1
                    )
                    status, health = await get_json(
                        app,
                        "/health"
                    )
                    self.assertEqual(status, 200)
                    self.assertTrue(
                        health["homeassistant"]["connected"]
                    )

                    _, area = await get_json(
                        app,
                        "/areas/kitchen"
                    )
                    _, device = await get_json(
                        app,
                        "/devices/device-1"
                    )
                    _, missing = await get_json(
                        app,
                        "/floors/missing"
                    )
                    self.assertEqual(
                        area["area_id"],
                        "kitchen"
                    )
                    self.assertEqual(
                        device["device_id"],
                        "device-1"
                    )
                    self.assertEqual(
                        missing,
                        {"error": "not found"}
                    )

                self.assertTrue(connector.stopped.is_set())
                self.assertFalse(connector.connected)
                self.assertTrue(
                    app.state.homeassistant_task.done()
                )

    async def test_websocket_routes_binary_audio_after_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "roomhub.db"
            connector = FakeConnector()
            FakeVoiceAudioConnection.instances.clear()

            with (
                patch.object(database, "DATABASE", database_path),
                patch(
                    "app.app_factory.VoiceAudioConnection",
                    FakeVoiceAudioConnection,
                ),
            ):
                app = create_app(
                    database_path=database_path,
                    homeassistant_connector=connector,
                )
                messages = iter([
                    {"type": "websocket.connect"},
                    {
                        "type": "websocket.receive",
                        "text": json.dumps({
                            "type": "endpoint.register",
                            "payload": {
                                "device_id": "kitchen-panel",
                                "device_name": "Kitchen Panel",
                                "room": "Kitchen",
                                "capabilities": ["microphone"],
                            },
                        }),
                    },
                    {
                        "type": "websocket.receive",
                        "bytes": b"\x01\x02",
                    },
                    {
                        "type": "websocket.receive",
                        "text": json.dumps({
                            "type": "voice.audio.end",
                            "source": "kitchen-panel",
                            "payload": {},
                        }),
                    },
                    {"type": "websocket.disconnect", "code": 1000},
                ])
                sent = []

                async def receive():
                    return next(messages)

                async def send(message):
                    sent.append(message)

                await app(
                    {
                        "type": "websocket",
                        "asgi": {"version": "3.0"},
                        "scheme": "ws",
                        "path": "/ws",
                        "raw_path": b"/ws",
                        "query_string": b"",
                        "headers": [],
                        "client": ("test", 1),
                        "server": ("test", 80),
                        "subprotocols": [],
                    },
                    receive,
                    send,
                )

            audio = FakeVoiceAudioConnection.instances[0]
            self.assertEqual(audio.frames, [b"\x01\x02"])
            self.assertEqual(audio.finished_for, "kitchen-panel")
            self.assertTrue(audio.closed)
            responses = [
                json.loads(message["text"])
                for message in sent
                if message["type"] == "websocket.send"
            ]
            self.assertEqual(
                [response["type"] for response in responses],
                ["endpoint.registered", "voice.intent.accepted"],
            )
