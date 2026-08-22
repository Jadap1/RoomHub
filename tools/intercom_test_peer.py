"""Temporary WebSocket peer for validating RoomHub intercom audio."""

import argparse
import asyncio
import hashlib
import hmac
import json
import math
import struct
from contextlib import suppress

import websockets


async def heartbeat(socket, endpoint_id: str) -> None:
    while True:
        await asyncio.sleep(5)
        await socket.send(json.dumps({
            "version": "1.0",
            "type": "endpoint.heartbeat",
            "source": endpoint_id,
            "target": "roomhub-core",
            "payload": {
                "connected": True,
                "privacy_state": "test_peer",
                "network_audio_allowed": False,
                "controls": {"microphone_muted": False, "volume": 65},
            },
        }))


async def register(socket, endpoint_id: str, room: str, token: str | None) -> None:
    challenge = json.loads(await socket.recv())
    if challenge.get("type") != "endpoint.challenge":
        raise RuntimeError("RoomHub did not provide a registration challenge")
    nonce = challenge.get("payload", {}).get("nonce", "")
    proof = None
    if token:
        key = bytes.fromhex(hashlib.sha256(token.encode()).hexdigest())
        proof = hmac.new(
            key, f"{nonce}:{endpoint_id}".encode(), hashlib.sha256
        ).hexdigest()
    payload = {
        "device_id": endpoint_id,
        "device_name": "RoomHub PC Test Peer",
        "room": room,
        "capabilities": ["speaker", "microphone"],
        "firmware_version": "test-peer",
    }
    if proof:
        payload["device_proof"] = proof
    await socket.send(json.dumps({
        "version": "1.0",
        "type": "endpoint.register",
        "source": endpoint_id,
        "target": "roomhub-core",
        "payload": payload,
    }))
    while True:
        message = await socket.recv()
        if isinstance(message, str):
            response = json.loads(message)
            if response.get("type") == "endpoint.registered":
                return
            if response.get("type") == "endpoint.registration_rejected":
                raise RuntimeError(response.get("payload", {}).get("reason"))


async def receive_test(url: str, token: str | None) -> None:
    endpoint_id = "intercom-pc-test"
    async with websockets.connect(url, max_size=65536) as socket:
        await register(socket, endpoint_id, "PC Test Receiver", token)
        keepalive = asyncio.create_task(heartbeat(socket, endpoint_id))
        print("READY: PC Test Receiver is registered", flush=True)
        received = 0
        peak = 0
        try:
            try:
                async with asyncio.timeout(180):
                    async for frame in socket:
                        if isinstance(frame, bytes):
                            received += len(frame)
                            if frame:
                                samples = struct.unpack(f"<{len(frame) // 2}h", frame)
                                peak = max(peak, max(abs(sample) for sample in samples))
                            continue
                        message = json.loads(frame)
                        message_type = message.get("type")
                        if message_type == "intercom.incoming":
                            call_id = message.get("payload", {}).get("call_id")
                            await socket.send(json.dumps({
                                "version": "1.0",
                                "type": "intercom.status",
                                "source": endpoint_id,
                                "target": "roomhub-core",
                                "payload": {
                                    "call_id": call_id,
                                    "status": "accepted",
                                },
                            }))
                            print(f"ACTIVE: accepted call {call_id}", flush=True)
                        elif message_type == "intercom.ended" and received:
                            seconds = received / (16000 * 2)
                            print(
                                f"COMPLETE: {received} PCM bytes, {seconds:.2f}s, peak={peak}",
                                flush=True,
                            )
                            return
            except TimeoutError:
                print(
                    f"TIMEOUT: {received} PCM bytes received, peak={peak}",
                    flush=True,
                )
        finally:
            keepalive.cancel()
            with suppress(asyncio.CancelledError):
                await keepalive


async def tone_test(url: str, target: str, token: str | None) -> None:
    endpoint_id = "intercom-pc-sender"
    async with websockets.connect(url, max_size=65536) as socket:
        await register(socket, endpoint_id, "PC Test Sender", token)
        await socket.send(json.dumps({
            "version": "1.0",
            "type": "intercom.start",
            "source": endpoint_id,
            "target": "roomhub-core",
            "payload": {
                "target_endpoint_id": target,
                "sample_rate": 16000,
                "channels": 1,
                "format": "pcm_s16le",
            },
        }))
        while True:
            message = await socket.recv()
            if not isinstance(message, str):
                continue
            response = json.loads(message)
            if response.get("type") == "intercom.rejected":
                raise RuntimeError(response.get("payload", {}).get("reason"))
            if response.get("type") == "intercom.ringing":
                call_id = response.get("payload", {}).get("call_id")
                print(f"RINGING: call {call_id}; accept it on the Tab5", flush=True)
                continue
            if response.get("type") == "intercom.active":
                call_id = response.get("payload", {}).get("call_id")
                break
        print("TRANSMITTING: two-second test tone", flush=True)
        frequency = 523.25
        amplitude = 5000
        frames_per_chunk = 320
        for offset in range(0, 16000 * 2, frames_per_chunk):
            samples = (
                int(amplitude * math.sin(2 * math.pi * frequency * index / 16000))
                for index in range(offset, offset + frames_per_chunk)
            )
            await socket.send(struct.pack(f"<{frames_per_chunk}h", *samples))
            await asyncio.sleep(frames_per_chunk / 16000)
        await socket.send(json.dumps({
            "version": "1.0",
            "type": "intercom.end",
            "source": endpoint_id,
            "target": "roomhub-core",
            "payload": {"call_id": call_id},
        }))
        print("COMPLETE", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("receive", "tone"))
    parser.add_argument("--url", default="ws://192.168.0.70:8000/ws")
    parser.add_argument("--target", default="tab5-01")
    parser.add_argument(
        "--token", help="fresh pairing credential or this peer's saved token"
    )
    args = parser.parse_args()
    asyncio.run(
        receive_test(args.url, args.token)
        if args.mode == "receive"
        else tone_test(args.url, args.target, args.token)
    )


if __name__ == "__main__":
    main()
