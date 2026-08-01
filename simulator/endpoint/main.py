import asyncio
import json
import websockets

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


async def main():

    async with websockets.connect(SERVER) as websocket:

        print("Connected to RoomHub Core")


        await websocket.send(
            encode_message(registration)
        )


        response = await websocket.recv()

        print("Server response:")
        print(response)


        asyncio.create_task(
            heartbeat_loop(websocket)
        )


        await receive_loop(websocket)


if __name__ == "__main__":

    asyncio.run(main())