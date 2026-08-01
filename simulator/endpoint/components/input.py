import json

from events import create_event


class InputComponent:

    def __init__(self, websocket, device_id):

        self.websocket = websocket
        self.device_id = device_id


    async def send_event(self, event_type, payload):

        event = create_event(
            event_type,
            self.device_id,
            payload
        )

        await self.websocket.send(
            json.dumps(event)
        )

        print(
            "[INPUT] Event sent:",
            event
        )