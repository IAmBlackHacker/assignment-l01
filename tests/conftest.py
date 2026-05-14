"""Shared test fixtures."""
from __future__ import annotations
from typing import AsyncIterator

import pytest

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.chat.events import Event


class FakeProvider:
    """Scripted provider: yields a pre-built list of events on each call.

    Supports multi-turn: each entry in `scripts` is one list of events that
    the next stream_turn() call returns.
    """
    name = "fake"
    model = "fake-1"

    def __init__(self, scripts: list[list[Event]]):
        self.scripts = scripts
        self.calls: list[dict] = []

    async def stream_turn(
        self, turns, tools, cancel: CancelToken, system=None,
    ) -> AsyncIterator[Event]:
        self.calls.append({"turns": list(turns), "tools": tools})
        if not self.scripts:
            return
        events = self.scripts.pop(0)
        for ev in events:
            if cancel.cancelled():
                return
            yield ev
