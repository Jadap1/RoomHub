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
from ...events.entity_events import (
    EntityCommandEvent,
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
from .providers.entity_provider import (
    HomeAssistantEntityProvider,
)
from .providers.area_provider import HomeAssistantAreaProvider
from .providers.device_provider import HomeAssistantDeviceProvider
from .providers.floor_provider import HomeAssistantFloorProvider
from .providers.state_provider import (
    HomeAssistantStateProvider,
)
from .providers.registry_updates import (
    HomeAssistantRegistryUpdates,
)
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
        self._entity_provider = (
            HomeAssistantEntityProvider(
                self._entity_filter,
                self._send_request
            )
        )
        self._state_provider = (
            HomeAssistantStateProvider(
                self._entity_provider,
                self._send_request
            )
        )
        self._floor_provider = HomeAssistantFloorProvider(self._send_request)
        self._area_provider = HomeAssistantAreaProvider(self._send_request)
        self._device_provider = HomeAssistantDeviceProvider(self._send_request)
        self._registry_updates = HomeAssistantRegistryUpdates(
            self._floor_provider,
            self._area_provider,
            self._device_provider,
            self._entity_provider,
            self._initial_state_sync,
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

        await self._registry_updates.stop()


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
            ping_timeout=20,
            max_size=16 * 1024 * 1024
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

            await self._initial_registry_sync()

            await self._initial_state_sync()

            await self._subscribe_to_state_changes()


            logger.info(
                "Home Assistant synchronisation "
                "complete"
            )


            await self._receive_task


    async def _initial_registry_sync(self) -> None:

        await self._floor_provider.sync()
        await self._area_provider.sync()
        await self._device_provider.sync()
        await self._entity_provider.sync_registry()


    async def _initial_state_sync(
        self
    ) -> None:

        states = await self._send_request(
            {
                "type": "get_states"
            }
        )

        await self._entity_provider.import_states(
            states,
            self._publish_state
        )


    async def _subscribe_to_state_changes(
        self
    ) -> None:

        await self._state_provider.subscribe(
        )
        await self._registry_updates.subscribe()

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

        await self._state_provider.handle_event(
            message
        )
        await self._registry_updates.handle_event(
            message
        )


    async def _publish_state(
        self,
        state_data: dict[str, Any]
    ) -> None:

        await self._state_provider.publish_state(
            state_data
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
