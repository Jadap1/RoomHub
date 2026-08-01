from screens.home import HomeScreen
from screens.lights import LightsScreen

class DisplayComponent:

    def __init__(self):

        self.current_screen = None
        self.state = None

        self.screens = {
            "home": HomeScreen(),
            "lights": LightsScreen()
        }


    async def show(self, screen_name, state):

        self.state = state

        screen = self.screens.get(screen_name)

        if not screen:
            print(f"[DISPLAY] Unknown screen {screen_name}")
            return

        self.current_screen = screen
        self.state.current_screen = screen_name

        print(f"[DISPLAY] Showing {screen_name}")

        state.current_screen = screen_name

        screen.render(state)