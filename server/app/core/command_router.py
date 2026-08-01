class CommandRouter:

    def __init__(self):
        self.commands = {}


    def register(self, command_type, handler):
        self.commands[command_type] = handler


    async def execute(self, message):

        command_type = message.get("type")

        handler = self.commands.get(command_type)

        if not handler:
            return {
                "version": "1.0",
                "type": "error",
                "payload": {
                    "message": f"Unknown command: {command_type}"
                }
            }

        return await handler(message)


command_router = CommandRouter()