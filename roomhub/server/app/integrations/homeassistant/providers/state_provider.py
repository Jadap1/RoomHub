import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ....core.event_bus import event_bus
from ....events.entity_events import (
    EntityStateChangedEvent,
)
from .entity_provider import (
    HomeAssistantEntityProvider,
)


logger = logging.getLogger(__name__)


class HomeAssistantStateProvider:

    def __init__(
        self,
        entity_provider: HomeAssistantEntityProvider,
        send_request: Callable[
            [dict[str, Any]],
            Awaitable[Any]
        ]
    ) -> None:

        self._entity_provider = entity_provider
        self._send_request = send_request


    async def subscribe(self) -> None:

        await self._send_request(
            {
                "type": "subscribe_events",
                "event_type": "state_changed"
            }
        )


    async def handle_event(
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


        if not self._entity_provider.allows(
            entity_id
        ):
            return


        if new_state is None:

            logger.info(
                "Home Assistant entity removed: %s",
                entity_id
            )

            return


        await self.publish_state(
            new_state
        )


    async def publish_state(
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

        await self._entity_provider.publish_discovered(
            state_data
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
