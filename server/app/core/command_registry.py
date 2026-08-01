from .command_router import command_router
from ..handlers.light_handler import handle_light_toggle


def register_commands():

    command_router.register(
        "light.toggle",
        handle_light_toggle
    )