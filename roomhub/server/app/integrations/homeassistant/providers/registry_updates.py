import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .area_provider import HomeAssistantAreaProvider
from .device_provider import HomeAssistantDeviceProvider
from .entity_provider import HomeAssistantEntityProvider
from .floor_provider import HomeAssistantFloorProvider


logger = logging.getLogger(__name__)

REGISTRY_EVENT_TYPES = {
    "floor_registry_updated",
    "area_registry_updated",
    "device_registry_updated",
    "entity_registry_updated",
}


class HomeAssistantRegistryUpdates:

    def __init__(
        self,
        floor_provider: HomeAssistantFloorProvider,
        area_provider: HomeAssistantAreaProvider,
        device_provider: HomeAssistantDeviceProvider,
        entity_provider: HomeAssistantEntityProvider,
        refresh_entity_states: Callable[
            [],
            Awaitable[None]
        ],
        send_request: Callable[
            [dict[str, Any]],
            Awaitable[Any]
        ]
    ) -> None:

        self._floor_provider = floor_provider
        self._area_provider = area_provider
        self._device_provider = device_provider
        self._entity_provider = entity_provider
        self._refresh_entity_states = (
            refresh_entity_states
        )
        self._send_request = send_request
        self._refresh_lock = asyncio.Lock()
        self._pending_event_types: set[str] = set()
        self._refresh_task: asyncio.Task | None = None


    async def subscribe(self) -> None:

        for event_type in REGISTRY_EVENT_TYPES:

            await self._send_request(
                {
                    "type": "subscribe_events",
                    "event_type": event_type
                }
            )


    async def handle_event(
        self,
        message: dict[str, Any]
    ) -> None:

        event_type = message.get(
            "event",
            {}
        ).get("event_type")

        if event_type not in REGISTRY_EVENT_TYPES:
            return

        self._pending_event_types.add(event_type)

        if (
            self._refresh_task is None
            or self._refresh_task.done()
        ):

            self._refresh_task = asyncio.create_task(
                self._refresh_pending()
            )
            self._refresh_task.add_done_callback(
                self._handle_refresh_result
            )


    async def stop(self) -> None:

        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None

        self._pending_event_types.clear()


    async def _refresh_pending(self) -> None:

        async with self._refresh_lock:

            while self._pending_event_types:

                event_types = self._pending_event_types
                self._pending_event_types = set()

                if "floor_registry_updated" in event_types:
                    await self._floor_provider.sync()

                if "area_registry_updated" in event_types:
                    await self._area_provider.sync()

                if "device_registry_updated" in event_types:
                    await self._device_provider.sync()

                if (
                    "device_registry_updated" in event_types
                    or "entity_registry_updated" in event_types
                ):
                    await self._entity_provider.sync_registry()
                    await self._refresh_entity_states()


    def _handle_refresh_result(
        self,
        task: asyncio.Task
    ) -> None:

        if task.cancelled():
            return

        error = task.exception()

        if error:
            logger.error(
                "Home Assistant registry refresh failed",
                exc_info=(
                    type(error),
                    error,
                    error.__traceback__
                )
            )
