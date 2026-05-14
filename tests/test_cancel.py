import asyncio
import pytest

from elyos_chat.chat.events import TextDelta, TurnEnd
from elyos_chat.chat.history import History
from elyos_chat.chat.session import ChatSession
from elyos_chat.tools.registry import ToolRegistry


class SlowProvider:
    name = "slow"
    model = "slow-1"
    def __init__(self, n=100):
        self.n = n

    async def stream_turn(self, turns, tools, cancel, system=None):
        for i in range(self.n):
            if cancel.cancelled():
                yield TurnEnd(reason="cancelled")
                return
            await asyncio.sleep(0.005)
            yield TextDelta(text=f"chunk{i}")
        yield TurnEnd(reason="stop")


class NoOpRenderer:
    def __init__(self): self.text = ""
    def write(self, t): self.text += t
    def begin_tool(self, n): pass
    def end_tool(self, n, r): pass
    def show_error(self, m): pass
    def turn_done(self): pass


class StubHttp:
    async def aclose(self): pass


async def test_cancel_mid_stream_unwinds_cleanly(tmp_path):
    session = ChatSession(
        provider=SlowProvider(n=100),
        registry=ToolRegistry(http=StubHttp()),
        history=History.new(tmp_path),
        renderer=NoOpRenderer(),
    )

    async def cancel_after_a_bit():
        await asyncio.sleep(0.03)
        session.cancel_current()

    await asyncio.gather(session.handle_user_input("go"), cancel_after_a_bit())

    snap = session.history.snapshot()
    assert snap[0].role == "user"
    assert snap[1].role == "assistant"
    assert snap[1].cancelled is True
    # Should have stopped well before completing all 100 chunks.
    assert len(snap[1].content) < len("chunk") * 100
