import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger(__name__)

EventHandler = Callable[[Any], Awaitable[None]]


@dataclass(frozen=True)
class PublishResult:
    event_type: str
    successful_handlers: int
    failed_handlers: int


class EventBus:

    def __init__(self) -> None:
        self._subscribers: dict[
            type,
            list[EventHandler]
        ] = defaultdict(list)


    def subscribe(
        self,
        event_class: type,
        handler: EventHandler
    ) -> None:

        handlers = self._subscribers[event_class]

        if handler not in handlers:
            handlers.append(handler)


    async def publish(
        self,
        event: Any
    ) -> PublishResult:

        handlers = list(
            self._subscribers.get(
                type(event),
                []
            )
        )

        successful_handlers = 0
        failed_handlers = 0

        for handler in handlers:

            try:
                await handler(event)
                successful_handlers += 1

            except Exception:
                failed_handlers += 1

                logger.exception(
                    "Event subscriber failed: "
                    "event=%s handler=%s",
                    type(event).__name__,
                    getattr(
                        handler,
                        "__qualname__",
                        repr(handler)
                    )
                )

        return PublishResult(
            event_type=type(event).__name__,
            successful_handlers=successful_handlers,
            failed_handlers=failed_handlers
        )


event_bus = EventBus()