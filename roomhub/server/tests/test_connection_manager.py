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


if __name__ == "__main__":
    unittest.main()
