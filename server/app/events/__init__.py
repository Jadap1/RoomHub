from collections import defaultdict


class EventBus:

    def __init__(self):

        self.subscribers = defaultdict(list)


    def subscribe(
        self,
        event_type,
        handler
    ):

        self.subscribers[
            event_type
        ].append(handler)


    async def publish(
        self,
        event
    ):

        event_type = event["type"]

        for handler in self.subscribers.get(
            event_type,
            []
        ):

            await handler(event)


event_bus = EventBus()