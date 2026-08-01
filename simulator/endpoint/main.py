import asyncio
import json
import websockets
import sys

from protocol import create_message, encode_message
from runtime import EndpointRuntime


SERVER = "ws://127.0.0.1:8000/ws"

DEVICE_ID = "kitchen-test-panel"

runtime = EndpointRuntime()
runtime.state.connected = True


registration = create_message(
    message_type="endpoint.register",
    source=DEVICE_ID,
    target="roomhub-core",
    payload={
        "device_id": DEVICE_ID,
        "device_name": "Kitchen Test Panel",
        "room": "Kitchen",
        "capabilities": [
            "display",
            "speaker",
            "microphone",
            "touch"
        ]
    }
)


async def heartbeat_loop(websocket):

    while True:

        await asyncio.sleep(10)

        heartbeat = create_message(
            message_type="endpoint.heartbeat",
            source=DEVICE_ID,
            target="roomhub-core",
            payload=runtime.state.as_dict()
        )
        print(registration)
        print("Sending Heartbeat:")
        print(heartbeat)

        await websocket.send(
            encode_message(heartbeat)
        )

        print("[HEARTBEAT] Sent")


async def receive_loop(websocket):

    while True:

        message = await websocket.recv()

        message = json.loads(message)

        print("\nMessage received:")
        print(message)

        await runtime.handle_message(message)

async def keyboard_loop():

    while True:

        key = await asyncio.to_thread(
            input,
            "\nPress 1/2/3: "
        )

        if key == "1":

            await runtime.input.send_event(
                "input.button",
                {
                    "button": "doorbell"
                }
            )


        elif key == "2":

            await runtime.input.send_event(
                "input.button",
                {
                    "button": "lights"
                }
            )


        elif key == "3":

            await runtime.input.send_event(
                "input.button",
                {
                    "button": "music"
                }
            )


        else:

            print("Unknown key")
""" async def test_input():

    while True:

        await asyncio.sleep(15)

        await runtime.input.button_press(
            "home"
        ) """


async def main():

    async with websockets.connect(SERVER) as websocket:

        print("Connected to RoomHub Core")

        runtime.attach_input(
            websocket,
            DEVICE_ID
        )

        print("Sending:")
        print(registration)

        await websocket.send(
            encode_message(registration)
        )


        response = await websocket.recv()

        print("Server response:")
        print(response)


        asyncio.create_task(
            heartbeat_loop(websocket)
        )
        asyncio.create_task(
            keyboard_loop()
        )


        await receive_loop(websocket)


if __name__ == "__main__":

    asyncio.run(main())