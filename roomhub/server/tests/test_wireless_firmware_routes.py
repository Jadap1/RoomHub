import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.app_factory import create_app
from app.core import database
from app.core.registry import registry
from app.models.endpoint import Endpoint
from app.services.wireless_firmware_service import WirelessFirmwareManifest


async def request(app, method, path, body=b"", headers=None):
    sent = []
    received = False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    encoded_headers = [
        (name.lower().encode(), value.encode())
        for name, value in (headers or {}).items()
    ]
    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": encoded_headers,
            "client": ("test", 1),
            "server": ("test", 80),
        },
        receive,
        send,
    )
    response_start = next(
        message for message in sent if message["type"] == "http.response.start"
    )
    response_body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return response_start["status"], json.loads(response_body)


class WirelessFirmwareRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        database_path = Path(self.directory.name) / "roomhub.db"
        self.database_patch = patch.object(database, "DATABASE", database_path)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        self.app = create_app(database_path=database_path)
        registry.endpoints.clear()
        self.addCleanup(registry.endpoints.clear)

    async def test_publish_requires_token_and_passes_image_to_service(self):
        manifest = WirelessFirmwareManifest(
            version="1.4.1",
            size=4,
            sha256="a" * 64,
            path="/firmware/wireless/image",
        )
        with (
            patch("app.app_factory.configured_firmware_token", return_value="secret"),
            patch("app.app_factory.firmware_token_valid", side_effect=lambda value: value == "secret"),
            patch("app.app_factory.wireless_firmware_service.publish", return_value=manifest) as publish,
            patch("app.app_factory.firmware_audit.record"),
        ):
            denied_status, _ = await request(
                self.app,
                "PUT",
                "/firmware/wireless",
                body=b"image",
                headers={"x-firmware-version": "1.4.1"},
            )
            accepted_status, accepted = await request(
                self.app,
                "PUT",
                "/firmware/wireless",
                body=b"image",
                headers={
                    "x-firmware-version": "1.4.1",
                    "x-roomhub-admin-token": "secret",
                },
            )

        self.assertEqual(denied_status, 401)
        self.assertEqual(accepted_status, 200)
        self.assertEqual(accepted["version"], "1.4.1")
        publish.assert_called_once_with("1.4.1", b"image")

    async def test_deploy_sends_authenticated_relative_image_command(self):
        manifest = WirelessFirmwareManifest(
            version="1.4.1",
            size=1234,
            sha256="b" * 64,
            path="/firmware/wireless/image",
        )
        registry.register(Endpoint(
            device_id="tab5-01",
            device_name="Bedroom panel",
            room="Master Bedroom",
            capabilities=["display"],
            connected=True,
        ))
        send = AsyncMock(return_value=True)
        with (
            patch("app.app_factory.configured_firmware_token", return_value="secret"),
            patch("app.app_factory.firmware_token_valid", return_value=True),
            patch("app.app_factory.wireless_firmware_service.manifest", return_value=manifest),
            patch("app.app_factory.secrets.token_urlsafe", return_value="request-id"),
            patch("app.app_factory.manager.send", new=send),
            patch("app.app_factory.firmware_audit.record"),
        ):
            status, response = await request(
                self.app,
                "POST",
                "/firmware/wireless/deploy/tab5-01",
                headers={"x-roomhub-admin-token": "secret"},
            )

        self.assertEqual(status, 200)
        self.assertEqual(response["status"], "sent")
        send.assert_awaited_once_with("tab5-01", {
            "version": "1.0",
            "type": "wireless.firmware.update",
            "target": "tab5-01",
            "payload": {
                "request_id": "request-id",
                "version": "1.4.1",
                "path": "/firmware/wireless/image",
                "size": 1234,
                "sha256": "b" * 64,
            },
        })


if __name__ == "__main__":
    unittest.main()
