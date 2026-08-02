class StateManager:

    def __init__(self):

        self.states = {}


    def update(self, device_id, state):

        self.states[device_id] = state


    def get(self, device_id):

        return self.states.get(device_id)


state_manager = StateManager()