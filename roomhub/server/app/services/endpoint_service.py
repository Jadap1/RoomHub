from ..models.endpoint import Endpoint
from ..core.registry import registry


def register_endpoint(data: dict):

    endpoint = Endpoint(**data)

    endpoint.connected = True

    registry.register(endpoint)

    return endpoint