from state import EndpointState
from components.display import DisplayComponent
from components.input import InputComponent


class EndpointRuntime:

    def __init__(self):

        self.state = EndpointState()

        self.display = DisplayComponent()

        self.input = None


    def attach_input(self, websocket, device_id):

        self.input = InputComponent(
            websocket,
            device_id
        )


    async def handle_message(self, message):

        message_type = message.get("type")


        if message_type == "display.show":

            await self.handle_display(message)


        elif message_type == "endpoint.heartbeat_ack":

            await self.handle_heartbeat_ack(message)

        elif message_type == "input.received":

            await self.handle_input_received(message)


        else:

            print(
                f"[RUNTIME] Unknown message type: {message_type}"
            )


    async def handle_display(self, message):

        await self.display.show(
            message["payload"]["screen"],
            self.state
        )


    async def handle_heartbeat_ack(self, message):

        timestamp = message["payload"].get("time")

        print(
            f"[HEARTBEAT] Acknowledged at {timestamp}"
        )
    async def handle_input_ack(self, message):

        print(
        "[INPUT] Core acknowledged event"
    ) 
    async def handle_input_received(self, message):

        status = message["payload"].get("status")

        print(
        f"[INPUT] Server acknowledged input: {status}"
    )
    