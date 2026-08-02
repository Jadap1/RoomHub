from collections.abc import Awaitable, Callable
from typing import Any

from ...events.entity_events import (
    EntityCommandEvent,
)


class HomeAssistantCommands:

    def __init__(
        self,
        send_request: Callable[
            [dict[str, Any]],
            Awaitable[Any]
        ]
    ) -> None:

        self._send_request = send_request


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
