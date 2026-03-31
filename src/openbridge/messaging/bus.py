"""Message bus for inter-component communication."""

from __future__ import annotations

import asyncio
from typing import Any, Callable
from collections import defaultdict

import structlog

logger = structlog.get_logger()


class MessageBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable[[Any], Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, channel: str, callback: Callable[[Any], Any]) -> None:
        async with self._lock:
            self._subscribers[channel].append(callback)
            logger.debug("subscribed", channel=channel)

    async def unsubscribe(self, channel: str, callback: Callable[[Any], Any]) -> None:
        async with self._lock:
            if channel in self._subscribers:
                self._subscribers[channel] = [
                    cb for cb in self._subscribers[channel] if cb != callback
                ]
            logger.debug("unsubscribed", channel=channel)

    async def publish(self, channel: str, message: Any) -> None:
        callbacks = self._subscribers.get(channel, [])
        if callbacks:
            await asyncio.gather(*[cb(message) for cb in callbacks], return_exceptions=True)
        logger.debug("published", channel=channel)

    async def request(self, channel: str, message: Any) -> list[Any]:
        callbacks = self._subscribers.get(channel, [])
        if not callbacks:
            return []

        results = await asyncio.gather(*[cb(message) for cb in callbacks], return_exceptions=True)
        return [r for r in results if not isinstance(r, Exception)]
