from ..core.entity_registry import entity_registry
from ..events.entity_events import EntityCommandEvent


class HomeAssistantConnector:

    def __init__(self) -> None:

        self.connected = False


    async def handle_entity_command(
        self,
        event: EntityCommandEvent
    ) -> None:

        await self.send_command(
            entity_id=event.entity_id,
            command=event.command,
            data=event.data
        )


    async def send_command(
        self,
        entity_id: str,
        command: str,
        data: dict | None = None
    ) -> None:

        print(
            "[HA COMMAND]",
            entity_id,
            command,
            data
        )

        # Temporary simulated Home Assistant response.
        # Remove this when the real HA connection is implemented.

        if command == "toggle":

            current_state = entity_registry.get_state(
                entity_id
            )

            current_value = (
                current_state.get("state")
                if current_state
                else "off"
            )

            new_state = (
                "off"
                if current_value == "on"
                else "on"
            )

            await self.receive_state(
                entity_id=entity_id,
                state=new_state
            )


    async def receive_state(
        self,
        entity_id: str,
        state: str,
        attributes: dict | None = None
    ) -> None:

        print(
            "[HA STATE]",
            entity_id,
            state
        )

        entity_registry.update_state(
            entity_id,
            state,
            attributes
        )