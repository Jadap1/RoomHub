import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.event_bus import PublishResult
from app.handlers.dispatcher import dispatch
from app.models.area import Area
from app.models.endpoint import Endpoint
from app.models.entity import Entity
from app.services.voice_intent_service import VoiceIntentService


class FakeRegistry:
    def __init__(self, items=None):
        self.entities = items or {}
        self.areas = items or {}
        self.endpoints = items or {}

    def get(self, item_id):
        return self.endpoints.get(item_id)


class VoiceIntentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entities = FakeRegistry({
            "light.kitchen_ceiling": Entity(
                entity_id="light.kitchen_ceiling",
                entity_type="light",
                name="Ceiling Light",
                area_id="kitchen",
            ),
            "light.study_ceiling": Entity(
                entity_id="light.study_ceiling",
                entity_type="light",
                name="Ceiling Light",
                area_id="study",
            ),
            "sensor.kitchen_temperature": Entity(
                entity_id="sensor.kitchen_temperature",
                entity_type="sensor",
                name="Temperature",
                area_id="kitchen",
            ),
            "light.dininglights": Entity(
                entity_id="light.dininglights",
                entity_type="light",
                name="DiningLights",
            ),
        })
        self.areas = FakeRegistry({
            "kitchen": Area(
                area_id="kitchen",
                name="Kitchen",
            ),
            "study": Area(
                area_id="study",
                name="Study",
            ),
        })
        self.endpoints = FakeRegistry({
            "kitchen-panel": Endpoint(
                device_id="kitchen-panel",
                device_name="Kitchen Panel",
                room="Kitchen",
                capabilities=["microphone"],
            ),
        })
        self.published = []

        async def publish(event):
            self.published.append(event)
            return PublishResult(
                event_type=type(event).__name__,
                successful_handlers=1,
                failed_handlers=0,
            )

        self.service = VoiceIntentService(
            entities=self.entities,
            areas=self.areas,
            endpoints=self.endpoints,
            publish=publish,
        )

    async def test_endpoint_room_disambiguates_friendly_name(self):
        response = await self.service.handle_transcript(
            "Please turn on the ceiling light",
            endpoint_id="kitchen-panel",
        )
        self.assertEqual(
            response["type"],
            "voice.intent.accepted",
        )
        self.assertEqual(
            response["payload"]["entity_id"],
            "light.kitchen_ceiling",
        )
        self.assertEqual(self.published[0].command, "turn_on")

    async def test_exact_entity_id_can_be_used(self):
        response = await self.service.handle_transcript(
            "turn off light.study_ceiling",
        )
        self.assertEqual(
            response["payload"]["entity_id"],
            "light.study_ceiling",
        )
        self.assertEqual(self.published[0].command, "turn_off")

    async def test_spoken_words_match_camel_case_friendly_name(self):
        response = await self.service.handle_transcript(
            "turn on dining lights",
        )

        self.assertEqual(response["type"], "voice.intent.accepted")
        self.assertEqual(
            response["payload"]["entity_id"],
            "light.dininglights",
        )
        self.assertEqual(self.published[0].command, "turn_on")

    async def test_ambiguous_name_is_rejected(self):
        response = await self.service.handle_transcript(
            "toggle ceiling light",
        )
        self.assertEqual(
            response["type"],
            "voice.intent.rejected",
        )
        self.assertEqual(
            response["payload"]["reason"],
            "ambiguous_entity",
        )
        self.assertEqual(
            response["payload"]["candidates"],
            [
                "light.kitchen_ceiling",
                "light.study_ceiling",
            ],
        )
        self.assertEqual(self.published, [])

    async def test_unknown_and_non_controllable_targets_are_rejected(self):
        for transcript in (
            "dim the ceiling light",
            "turn on temperature",
            "turn on missing light",
        ):
            with self.subTest(transcript=transcript):
                response = await self.service.handle_transcript(
                    transcript,
                    area_id="kitchen",
                )
                self.assertEqual(
                    response["type"],
                    "voice.intent.rejected",
                )
        self.assertEqual(self.published, [])

    async def test_failed_command_delivery_is_reported(self):
        async def failed_publish(event):
            return PublishResult(
                event_type=type(event).__name__,
                successful_handlers=0,
                failed_handlers=1,
            )

        service = VoiceIntentService(
            entities=self.entities,
            areas=self.areas,
            endpoints=self.endpoints,
            publish=failed_publish,
        )
        response = await service.handle_transcript(
            "turn on ceiling light",
            area_id="kitchen",
        )
        self.assertEqual(
            response["type"],
            "voice.intent.failed",
        )

    async def test_dispatcher_validates_and_routes_transcript(self):
        fake_service = SimpleNamespace(
            handle_transcript=AsyncMock(
                return_value={
                    "version": "1.0",
                    "type": "voice.intent.accepted",
                    "payload": {"status": "accepted"},
                }
            )
        )
        with patch(
            "app.handlers.voice_handler.voice_intent_service",
            fake_service,
        ):
            response = await dispatch({
                "version": "1.0",
                "type": "voice.transcript",
                "source": "kitchen-panel",
                "target": "roomhub-core",
                "payload": {
                    "text": "turn on ceiling light",
                    "area_id": "kitchen",
                },
            })

        self.assertEqual(
            response["type"],
            "voice.intent.accepted",
        )
        fake_service.handle_transcript.assert_awaited_once_with(
            transcript="turn on ceiling light",
            endpoint_id="kitchen-panel",
            area_id="kitchen",
        )

    async def test_dispatcher_rejects_empty_transcript(self):
        response = await dispatch({
            "type": "voice.transcript",
            "payload": {"text": "  "},
        })
        self.assertEqual(
            response["payload"]["reason"],
            "invalid_transcript",
        )
