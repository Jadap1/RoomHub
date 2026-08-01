class EndpointState:

    def __init__(self):

        self.connected = False
        self.current_screen = None


    def as_dict(self):

        return {
            "connected": self.connected,
            "screen": self.current_screen
        }