from .base import Screen


class HomeScreen(Screen):

    name = "home"


    def render(self, state):

        print()
        print("================================")
        print("        ROOM HUB HOME")
        print("================================")
        print(f"Connected : {state.connected}")
        print()
        print("1. Doorbell")
        print("2. Lights")
        print("3. Music")
        print("================================")