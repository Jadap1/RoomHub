import unittest

from app.core.connection_manager import ConnectionManager


class ConnectionManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_socket_cannot_remove_replacement(self):
        manager = ConnectionManager()
        old_socket = object()
        replacement = object()

        await manager.connect("panel", old_socket)
        await manager.connect("panel", replacement)

        self.assertFalse(manager.disconnect("panel", old_socket))
        self.assertIs(manager.get("panel"), replacement)
        self.assertTrue(manager.disconnect("panel", replacement))
        self.assertIsNone(manager.get("panel"))

    async def test_sends_json_and_binary_frames(self):
        class Socket:
            def __init__(self):
                self.frames = []

            async def send_json(self, message):
                self.frames.append(("json", message))

            async def send_bytes(self, data):
                self.frames.append(("bytes", data))

        manager = ConnectionManager()
        socket = Socket()
        await manager.connect("panel", socket)
        self.assertTrue(await manager.send("panel", {"type": "test"}))
        self.assertTrue(await manager.send_bytes("panel", b"\x01\x00"))
        self.assertEqual(socket.frames, [
            ("json", {"type": "test"}),
            ("bytes", b"\x01\x00"),
        ])


if __name__ == "__main__":
    unittest.main()
