"""Cooperative cancellation primitive used across a single turn."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field


@dataclass
class CancelToken:
    event: asyncio.Event = field(default_factory=asyncio.Event)

    def cancel(self) -> None:
        self.event.set()

    def cancelled(self) -> bool:
        return self.event.is_set()

    async def wait(self) -> None:
        await self.event.wait()
