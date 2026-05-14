"""Provider Protocol — the only seam between the chat loop and SDKs.

Every adapter:
  1. Translates canonical Turn list to SDK message shape.
  2. Translates SDK tool-schema list (registry.for_<name>()).
  3. Streams SDK events into canonical Event objects.
  4. Cooperates with CancelToken — closes the stream cleanly on cancel.
"""
from __future__ import annotations
from typing import AsyncIterator, Protocol

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.chat.events import Event
from elyos_chat.chat.history import Turn


class Provider(Protocol):
    name: str
    model: str

    async def stream_turn(
        self,
        turns: list[Turn],
        tools: list[dict],            # provider-specific tool definitions
        cancel: CancelToken,
        system: str | None = None,
    ) -> AsyncIterator[Event]:
        ...
