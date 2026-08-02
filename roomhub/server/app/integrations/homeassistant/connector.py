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
from .authentication import authenticate
from .commands import HomeAssistantCommands
from .request_client import (
    HomeAssistantRequestClient,
)


logger = logging.getLogger(__name__)


class HomeAssistantConnector:

    def __init__(self) -> None:

        self.connected = False

        self._websocket = None

        self._receive_task = None
        self._stop_requested = False

        self._entity_filter = (
            self._load_entity_filter()
        )
        self._request_client = (
            HomeAssistantRequestClient()
        )
        self._commands = HomeAssistantCommands(
            self._send_request
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
            self._request_client.detach()
            self._request_client.fail_pending_requests(
                ConnectionError(
                    "Home Assistant connection was lost"
                )
            )

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

            self._request_client.attach(websocket)
            self._websocket = websocket

            await authenticate(
                websocket,
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

            await self._initial_state_sync()

            await self._subscribe_to_state_changes()


            logger.info(
                "Home Assistant synchronisation "
                "complete"
            )


            await self._receive_task


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
        payload: dict[str, Any]
    ) -> Any:

        if not self.connected:
            raise RuntimeError(
                "Home Assistant is not connected"
            )

        return await self._request_client.send_request(
            payload
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

                    self._request_client.handle_result(
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

        await self._commands.handle_entity_command(
            event
        )


    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: str,
        service_data: dict | None = None
    ) -> None:

        await self._commands.call_service(
            domain=domain,
            service=service,
            entity_id=entity_id,
            service_data=service_data
        )
