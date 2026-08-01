import asyncio
import json
import websockets


SERVER = "ws://localhost:8000/ws"


endpoint = {
    "type": "register",
    "device_id": "kitchen-test-panel",
    "device_name": "Kitchen Test Panel",
    "room": "Kitchen",
    "capabilities": [
        "display",
        "speaker",
        "microphone",
        "touch"
    ]
}


async def main():

    async with websockets.connect(SERVER) as websocket:

        print("Connected to RoomHub Core")

        await websocket.send(
            json.dumps(endpoint)
        )

        response = await websocket.recv()

        print("Server response:")
        print(response)

        while True:
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())