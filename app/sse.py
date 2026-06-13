import asyncio
import json
from typing import Any, AsyncIterator


class EventBroker:
    """Simple in-memory pub/sub for Server-Sent Events.

    Each subscriber gets its own asyncio.Queue. Publishing puts the
    event on every subscriber's queue.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            await queue.put(event)

    async def stream(self) -> AsyncIterator[str]:
        queue = self.subscribe()
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            self.unsubscribe(queue)


broker = EventBroker()
