class Display:

    def __init__(self):
        self.current_screen = None


    async def show(self, screen):

        self.current_screen = screen

        print(
            f"[DISPLAY] Showing screen: {screen}"
        )