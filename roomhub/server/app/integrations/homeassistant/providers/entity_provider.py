import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ....core.event_bus import event_bus
from ....core.entity_registry import entity_registry
from ....events.entity_events import (
    EntityDiscoveredEvent,
    EntityRemovedEvent,
)
from ...homeassistant_config import (
    EntityFilterConfig,
)


logger = logging.getLogger(__name__)


class HomeAssistantEntityProvider:

    def __init__(
        self,
        entity_filter: EntityFilterConfig,
        send_request: Callable[
            [dict[str, Any]],
            Awaitable[Any]
        ],
        get_device_area_id: Callable[
            [str],
            str | None
        ]
    ) -> None:

        self._entity_filter = entity_filter
        self._send_request = send_request
        self._get_device_area_id = (
            get_device_area_id
        )
        self._registry_entries: dict[
            str,
            dict[str, Any]
        ] = {}


    async def sync_registry(self) -> None:

        entries = await self._send_request(
            {
                "type": "config/entity_registry/list"
            }
        )

        known_entity_ids = set(
            self._registry_entries
        )

        if not known_entity_ids:
            known_entity_ids = {
                entity_id
                for entity_id, entity in (
                    entity_registry.entities.items()
                )
                if entity.integration == "homeassistant"
            }

        registry_entries = {
            entry["entity_id"]: entry
            for entry in entries
            if entry.get("entity_id")
        }

        for entity_id in (
            known_entity_ids
            - set(registry_entries)
        ):
            await event_bus.publish(
                EntityRemovedEvent(
                    entity_id=entity_id
                )
            )

        self._registry_entries = registry_entries

        logger.info(
            "Imported %s Home Assistant entity "
            "registry entries",
            len(self._registry_entries)
        )


    def allows(
        self,
        entity_id: str
    ) -> bool:

        return self._entity_filter.allows(
            entity_id
        )


    async def import_states(
        self,
        states: list[dict[str, Any]],
        publish_state: Callable[
            [dict[str, Any]],
            Awaitable[None]
        ]
    ) -> None:

        imported_count = 0

        for state_data in states:

            entity_id = state_data.get(
                "entity_id"
            )

            if not entity_id:
                continue

            if not self.allows(
                entity_id
            ):
                continue


            await publish_state(
                state_data
            )

            imported_count += 1


        logger.info(
            "Imported %s Home Assistant entities",
            imported_count
        )


    async def publish_discovered(
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

        registry_entry = self._registry_entries.get(
            entity_id,
            {}
        )

        device_id = registry_entry.get(
            "device_id"
        )

        area_id = registry_entry.get(
            "area_id"
        )

        if area_id is None and device_id:
            area_id = self._get_device_area_id(
                device_id
            )


        await event_bus.publish(
            EntityDiscoveredEvent(
                entity_id=entity_id,
                entity_type=entity_type,
                name=friendly_name,
                device_id=device_id,
                area_id=area_id,
                platform=registry_entry.get(
                    "platform"
                ),
                entity_category=registry_entry.get(
                    "entity_category"
                ),
                attributes=attributes
            )
        )
