import asyncio
import json
import logging
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from ...config_sources import (
    is_homeassistant_app,
    load_app_options,
)
from ...core.event_bus import event_bus
from ...events.entity_events import (
    EntityCommandEvent,
    EntityDiscoveredEvent,
    EntityStateChangedEvent,
    FloorDiscoveredEvent,
    AreaDiscoveredEvent,
    DeviceDiscoveredEvent,
)
from ..homeassistant_auth import (
    get_homeassistant_connection_settings,
)
from ..homeassistant_config import (
    EntityFilterConfig,
)
from ..homeassistant_config_loader import (
    load_homeassistant_config,
)


logger = logging.getLogger(__name__)


class HomeAssistantConnector:

    def __init__(self) -> None:

        self.connected = False

        self._websocket = None
        self._next_message_id = 1

        self._pending_requests: dict[
            int,
            asyncio.Future
        ] = {}

        self._receive_task = None
        self._stop_requested = False

        self._entity_filter = (
            self._load_entity_filter()
        )


    def _load_entity_filter(
        self
    ) -> EntityFilterConfig:

        if is_homeassistant_app():

            options = load_app_options()

            return (
                EntityFilterConfig
                .model_validate(
                    options.get(
                        "entity_filter",
                        {}
                    )
                )
            )


        return (
            load_homeassistant_config()
            .entity_filter
        )


    def _new_message_id(self) -> int:

        message_id = self._next_message_id

        self._next_message_id += 1

        return message_id


    async def start(self) -> None:

        self._stop_requested = False

        while not self._stop_requested:

            try:

                await self._run_connection()

            except asyncio.CancelledError:

                raise

            except Exception:

                logger.exception(
                    "Home Assistant connection failed"
                )


            self.connected = False
            self._fail_pending_requests()

            if not self._stop_requested:

                delay = (
                    self._get_reconnect_delay()
                )

                logger.warning(
                    "Reconnecting to Home Assistant "
                    "in %s seconds",
                    delay
                )

                await asyncio.sleep(delay)


    async def stop(self) -> None:

        self._stop_requested = True
        self.connected = False

        if self._websocket:

            await self._websocket.close()

        if self._receive_task:

            self._receive_task.cancel()


    def _get_reconnect_delay(self) -> int:

        if is_homeassistant_app():

            options = load_app_options()

            return int(
                options.get(
                    "reconnect_delay_seconds",
                    5
                )
            )


        return (
            load_homeassistant_config()
            .reconnect_delay_seconds
        )


    async def _run_connection(self) -> None:

        settings = (
            get_homeassistant_connection_settings()
        )

        logger.info(
            "Connecting to Home Assistant: "
            "mode=%s url=%s",
            settings.mode,
            settings.websocket_url
        )


        async with websockets.connect(
            settings.websocket_url,
            open_timeout=20,
            ping_interval=30,
            ping_timeout=20
        ) as websocket:

            self._websocket = websocket

            await self._authenticate(
                settings.access_token
            )

            self.connected = True

            logger.info(
                "Authenticated with Home Assistant"
            )


            self._receive_task = (
                asyncio.create_task(
                    self._receive_loop()
                )
            )
        async def _synchronise_registries(
            self
        ) -> None:

            await self._synchronise_floors()
            await self._synchronise_areas()
            await self._synchronise_devices()
            await self._synchronise_entity_registry()


            await self._initial_state_sync()

            await self._subscribe_to_state_changes()


            logger.info(
                "Home Assistant synchronisation "
                "complete"
            )


            await self._receive_task


    async def _authenticate(
        self,
        access_token: str
    ) -> None:

        initial_message = json.loads(
            await self._websocket.recv()
        )

        if (
            initial_message.get("type")
            != "auth_required"
        ):

            raise RuntimeError(
                "Home Assistant did not request "
                "authentication"
            )


        await self._websocket.send(
            json.dumps(
                {
                    "type": "auth",
                    "access_token": access_token
                }
            )
        )


        auth_response = json.loads(
            await self._websocket.recv()
        )

        response_type = auth_response.get(
            "type"
        )

        if response_type == "auth_invalid":

            raise RuntimeError(
                "Home Assistant authentication "
                "failed: "
                f"{auth_response.get('message')}"
            )


        if response_type != "auth_ok":

            raise RuntimeError(
                "Unexpected Home Assistant "
                "authentication response: "
                f"{auth_response}"
            )


    async def _initial_state_sync(
        self
    ) -> None:

        states = await self._send_request(
            {
                "type": "get_states"
            }
        )

        imported_count = 0

        for state_data in states:

            entity_id = state_data.get(
                "entity_id"
            )

            if not entity_id:
                continue

            if not self._entity_filter.allows(
                entity_id
            ):
                continue


            await self._publish_state(
                state_data
            )

            imported_count += 1


        logger.info(
            "Imported %s Home Assistant entities",
            imported_count
        )


    async def _subscribe_to_state_changes(
        self
    ) -> None:

        await self._send_request(
            {
                "type": "subscribe_events",
                "event_type": "state_changed"
            }
        )


    async def _send_request(
        self,
        message: dict[str, Any]
    ) -> Any:

        if not self.connected:
            raise RuntimeError(
                "Home Assistant is not connected"
            )


        message_id = self._new_message_id()

        outgoing_message = {
            "id": message_id,
            **message
        }


        loop = asyncio.get_running_loop()

        future = loop.create_future()

        self._pending_requests[
            message_id
        ] = future


        try:

            await self._websocket.send(
                json.dumps(
                    outgoing_message
                )
            )

            return await asyncio.wait_for(
                future,
                timeout=30
            )

        finally:

            self._pending_requests.pop(
                message_id,
                None
            )


    async def _receive_loop(self) -> None:

        try:

            async for raw_message in (
                self._websocket
            ):

                message = json.loads(
                    raw_message
                )

                message_type = message.get(
                    "type"
                )


                if message_type == "result":

                    self._handle_result(
                        message
                    )


                elif message_type == "event":

                    await self._handle_event(
                        message
                    )


                elif message_type == "pong":

                    logger.debug(
                        "Home Assistant pong received"
                    )


                else:

                    logger.debug(
                        "Unhandled Home Assistant "
                        "message: %s",
                        message
                    )


        except ConnectionClosed as error:

            logger.warning(
                "Home Assistant WebSocket closed: "
                "%s",
                error
            )

            raise


    def _handle_result(
        self,
        message: dict[str, Any]
    ) -> None:

        message_id = message.get("id")

        future = self._pending_requests.get(
            message_id
        )

        if not future or future.done():
            return


        if message.get("success"):

            future.set_result(
                message.get("result")
            )

            return


        error = message.get(
            "error",
            {}
        )

        future.set_exception(
            RuntimeError(
                "Home Assistant request failed: "
                f"{error.get('code')} - "
                f"{error.get('message')}"
            )
        )


    async def _handle_event(
        self,
        message: dict[str, Any]
    ) -> None:

        event = message.get(
            "event",
            {}
        )

        if (
            event.get("event_type")
            != "state_changed"
        ):

            return


        event_data = event.get(
            "data",
            {}
        )

        entity_id = event_data.get(
            "entity_id"
        )

        new_state = event_data.get(
            "new_state"
        )


        if not entity_id:
            return


        if not self._entity_filter.allows(
            entity_id
        ):
            return


        if new_state is None:

            logger.info(
                "Home Assistant entity removed: %s",
                entity_id
            )

            return


        await self._publish_state(
            new_state
        )


    async def _publish_state(
        self,
        state_data: dict[str, Any]
    ) -> None:

        entity_id = state_data[
            "entity_id"
        ]

        attributes = state_data.get(
            "attributes",
            {}
        )

        friendly_name = attributes.get(
            "friendly_name",
            entity_id
        )

        entity_type = entity_id.split(
            ".",
            1
        )[0]


        await event_bus.publish(
            EntityDiscoveredEvent(
                entity_id=entity_id,
                entity_type=entity_type,
                name=friendly_name,
                attributes=attributes
            )
        )


        state_value = state_data.get(
            "state",
            "unknown"
        )

        available = state_value not in {
            "unavailable",
            "unknown"
        }


        await event_bus.publish(
            EntityStateChangedEvent(
                entity_id=entity_id,
                state=state_value,
                attributes=attributes,
                available=available
            )
        )


    async def handle_entity_command(
        self,
        event: EntityCommandEvent
    ) -> None:

        domain = event.entity_id.split(
            ".",
            1
        )[0]

        await self.call_service(
            domain=domain,
            service=event.command,
            entity_id=event.entity_id,
            service_data=event.data
        )


    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: str,
        service_data: dict | None = None
    ) -> None:

        await self._send_request(
            {
                "type": "call_service",
                "domain": domain,
                "service": service,
                "service_data": (
                    service_data or {}
                ),
                "target": {
                    "entity_id": entity_id
                }
            }
        )


    def _fail_pending_requests(
        self
    ) -> None:

        for future in (
            self._pending_requests.values()
        ):

            if not future.done():

                future.set_exception(
                    ConnectionError(
                        "Home Assistant connection "
                        "was lost"
                    )
                )


        self._pending_requests.clear()
async def _synchronise_floors(self) -> None:

    floors = await self._send_request(
        {
            "type": "config/floor_registry/list"
        }
    )

    for floor in floors:

        await event_bus.publish(
            FloorDiscoveredEvent(
                floor_id=floor["floor_id"],
                name=floor["name"],
                level=floor.get("level")
            )
        )


async def _synchronise_areas(self) -> None:

    areas = await self._send_request(
        {
            "type": "config/area_registry/list"
        }
    )

    for area in areas:

        await event_bus.publish(
            AreaDiscoveredEvent(
                area_id=area["area_id"],
                name=area["name"],
                floor_id=area.get("floor_id")
            )
        )


async def _synchronise_devices(self) -> None:

    devices = await self._send_request(
        {
            "type": "config/device_registry/list"
        }
    )

    for device in devices:

        name = (
            device.get("name_by_user")
            or device.get("name")
            or device.get("default_name")
            or device["id"]
        )

        await event_bus.publish(
            DeviceDiscoveredEvent(
                device_id=device["id"],
                name=name,
                area_id=device.get("area_id"),
                manufacturer=(
                    device.get("manufacturer")
                    or device.get(
                        "default_manufacturer"
                    )
                ),
                model=(
                    device.get("model")
                    or device.get("default_model")
                ),
                config_entries=device.get(
                    "config_entries",
                    []
                ),
                via_device_id=device.get(
                    "via_device_id"
                )
            )
        )