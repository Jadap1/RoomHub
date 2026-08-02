import json
import unittest

from app.integrations.homeassistant.authentication import authenticate


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = iter(json.dumps(message) for message in messages)
        self.sent = []

    async def recv(self):
        return next(self.messages)

    async def send(self, message):
        self.sent.append(json.loads(message))


class AuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_authenticates_with_access_token(self):
        websocket = FakeWebSocket([
            {"type": "auth_required"},
            {"type": "auth_ok"},
        ])
        await authenticate(websocket, "token")
        self.assertEqual(websocket.sent, [{"type": "auth", "access_token": "token"}])

    async def test_rejects_invalid_authentication(self):
        websocket = FakeWebSocket([
            {"type": "auth_required"},
            {"type": "auth_invalid", "message": "bad token"},
        ])
        with self.assertRaisesRegex(RuntimeError, "authentication failed: bad token"):
            await authenticate(websocket, "token")

    async def test_rejects_unexpected_messages(self):
        with self.assertRaisesRegex(RuntimeError, "did not request authentication"):
            await authenticate(FakeWebSocket([{"type": "auth_ok"}]), "token")

        with self.assertRaisesRegex(RuntimeError, "Unexpected Home Assistant"):
            await authenticate(FakeWebSocket([
                {"type": "auth_required"},
                {"type": "event"},
            ]), "token")
