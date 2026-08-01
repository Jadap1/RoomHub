from components.display import Display
from components.audio import Audio
from components.microphone import Microphone


class EndpointRuntime:

    def __init__(self):

        self.display = Display()
        self.audio = Audio()
        self.microphone = Microphone()


    async def handle_message(self, message):

        message_type = message.get("type")

        payload = message.get("payload", {})


        if message_type == "display.show":

            await self.display.show(
                payload.get("screen")
            )


        elif message_type == "audio.play":

            await self.audio.play(
                payload.get("audio")
            )


        else:

            print(
                f"[RUNTIME] Unknown message: {message_type}"
            )