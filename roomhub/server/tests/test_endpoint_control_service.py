import unittest
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from app.models.endpoint import Endpoint
from app.services.endpoint_control_service import EndpointControlRequest, EndpointControlService


class EndpointControlServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_bounded_controls_to_connected_endpoint(self):
        service = EndpointControlService()
        endpoint = Endpoint(device_id="panel", device_name="Panel", room="Bedroom", capabilities=["display", "speaker"], connected=True)
        with patch("app.services.endpoint_control_service.registry.get", return_value=endpoint), patch("app.services.endpoint_control_service.manager.get", return_value=object()), patch("app.services.endpoint_control_service.manager.send", new=AsyncMock(return_value=True)) as send:
            result = await service.apply("panel", EndpointControlRequest(screen_on=False, volume=42))
        self.assertEqual(result["status"], "sent")
        message = send.await_args.args[1]
        self.assertEqual(message["type"], "endpoint.control")
        self.assertEqual(message["payload"]["screen_on"], False)
        self.assertEqual(message["payload"]["volume"], 42)

    async def test_reports_unavailable_endpoint_without_sending(self):
        service = EndpointControlService()
        endpoint = Endpoint(device_id="panel", device_name="Panel", room="Bedroom", capabilities=["display"], connected=False)
        with patch("app.services.endpoint_control_service.registry.get", return_value=endpoint), patch("app.services.endpoint_control_service.manager.send", new=AsyncMock()) as send:
            result = await service.apply("panel", EndpointControlRequest(screen_on=True))
        self.assertEqual(result["status"], "unavailable")
        send.assert_not_awaited()

    def test_rejects_empty_or_out_of_range_controls(self):
        with self.assertRaises(ValidationError):
            EndpointControlRequest()
        with self.assertRaises(ValidationError):
            EndpointControlRequest(volume=101)

    def test_acknowledgement_updates_endpoint_control_state(self):
        service = EndpointControlService()
        endpoint = Endpoint(device_id="panel", device_name="Panel", room="Bedroom", capabilities=["display", "speaker"], connected=True)
        with patch("app.services.endpoint_control_service.registry.get", return_value=endpoint):
            response = service.update("panel", {"request_id": "request-1", "status": "applied", "screen_on": False, "volume": 42})
        self.assertEqual(endpoint.state["controls"], {"screen_on": False, "volume": 42})
        self.assertEqual(response["type"], "endpoint.control.ack")
