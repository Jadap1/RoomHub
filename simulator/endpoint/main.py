import asyncio
import websockets

from protocol import create_message, encode_message


SERVER = "ws://127.0.0.1:8000/ws"

DEVICE_ID = "kitchen-test-panel"


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


async def main():

    async with websockets.connect(SERVER) as websocket:

        print("Connected to RoomHub Core")

        await websocket.send(
            encode_message(registration)
        )

        response = await websocket.recv()

        print("Server response:")
        print(response)

        while True:
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())