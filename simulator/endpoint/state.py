from datetime import datetime


class EndpointState:

    def __init__(self):

        self.screen = "home"
        self.connected = False
        self.started = datetime.now()


    def as_dict(self):

        return {
            "screen": self.screen,
            "connected": self.connected,
            "uptime": str(
                datetime.now() - self.started
            )
        }