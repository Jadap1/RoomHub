from state import EndpointState
from components.display import DisplayComponent


class EndpointRuntime:

    def __init__(self):

        self.state = EndpointState()

        self.display = DisplayComponent()


    async def handle_message(self, message):

        message_type = message.get("type")


        if message_type == "display.show":

            await self.handle_display(message)


        elif message_type == "endpoint.heartbeat_ack":

            await self.handle_heartbeat_ack(message)


        else:

            print(
                f"[RUNTIME] Unknown message type: {message_type}"
            )


    async def handle_display(self, message):

        screen = message["payload"].get("screen")

        self.display.show(screen)


    async def handle_heartbeat_ack(self, message):

        timestamp = message["payload"].get("time")

        print(
            f"[HEARTBEAT] Acknowledged at {timestamp}"
        )