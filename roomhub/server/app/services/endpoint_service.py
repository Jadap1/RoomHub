from ..models.endpoint import Endpoint
from ..core.registry import registry
from .endpoint_assignment_service import endpoint_assignment_service


def register_endpoint(data: dict):

    endpoint = Endpoint(**data)

    endpoint.connected = True

    endpoint_assignment_service.apply(endpoint)

    registry.register(endpoint)

    return endpoint
