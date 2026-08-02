from ..models.endpoint import Endpoint


class EndpointRegistry:

    def __init__(self):
        self.endpoints = {}


    def register(self, endpoint: Endpoint):

        self.endpoints[endpoint.device_id] = endpoint


    def get_all(self):
        return {
            key: value.model_dump()
            for key, value in self.endpoints.items()
        }


    def get(self, device_id):

        return self.endpoints.get(device_id)


registry = EndpointRegistry()