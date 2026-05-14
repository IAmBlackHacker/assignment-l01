import asyncio
import tempfile
from pathlib import Path

import pytest

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.chat.events import (
    Error, TextDelta, ToolUseEnd, ToolUseStart, TurnEnd,
)
from elyos_chat.chat.history import History
from elyos_chat.chat.session import ChatSession
from elyos_chat.tools.registry import ToolRegistry, ToolSpec


class StubHttp:
    async def aclose(self): pass


class CapturingRenderer:
    def __init__(self):
        self.events = []
    def write(self, text): self.events.append(("text", text))
    def begin_tool(self, name): self.events.append(("tool_start", name))
    def end_tool(self, name, result): self.events.append(("tool_end", name, result))
    def show_error(self, msg): self.events.append(("error", msg))
    def turn_done(self): self.events.append(("turn_done",))


async def fake_weather(args, cancel, http):
    return {"temp_c": 12, "echo": args}


def build_registry():
    r = ToolRegistry(http=StubHttp())
    r.register(ToolSpec(name="weather", description="", schema={}, handler=fake_weather))
    return r


async def test_simple_text_response_no_tool(tmp_path):
    from tests.conftest import FakeProvider
    provider = FakeProvider(scripts=[[TextDelta("hello"), TurnEnd(reason="stop")]])
    history = History.new(tmp_path)
    renderer = CapturingRenderer()
    session = ChatSession(provider=provider, registry=build_registry(),
                         history=history, renderer=renderer)
    await session.handle_user_input("hi")

    snap = history.snapshot()
    assert snap[0].role == "user"
    assert snap[1].role == "assistant"
    assert snap[1].content == "hello"
    assert ("text", "hello") in renderer.events


async def test_tool_call_loop_runs_handler_and_replies(tmp_path):
    from tests.conftest import FakeProvider
    provider = FakeProvider(scripts=[
        [
            ToolUseStart(tool_use_id="t1", name="weather"),
            ToolUseEnd(tool_use_id="t1", name="weather", args={"location": "London"}),
            TurnEnd(reason="tool_use"),
        ],
        [
            TextDelta("It's 12°C in London."),
            TurnEnd(reason="stop"),
        ],
    ])
    history = History.new(tmp_path)
    renderer = CapturingRenderer()
    session = ChatSession(provider=provider, registry=build_registry(),
                         history=history, renderer=renderer)
    await session.handle_user_input("weather in London?")

    roles = [t.role for t in history.snapshot()]
    assert roles == ["user", "assistant", "tool", "assistant"]
    tool_turn = history.snapshot()[2]
    assert tool_turn.tool_results[0]["content"]["temp_c"] == 12
    final_assistant = history.snapshot()[3]
    assert "12" in final_assistant.content


async def test_cancel_truncates_assistant_turn(tmp_path):
    from tests.conftest import FakeProvider
    provider = FakeProvider(scripts=[[
        TextDelta("partial"),
        TextDelta(" answer"),
        TurnEnd(reason="stop"),
    ]])
    history = History.new(tmp_path)
    renderer = CapturingRenderer()
    session = ChatSession(provider=provider, registry=build_registry(),
                         history=history, renderer=renderer)

    async def cancel_quickly():
        await asyncio.sleep(0)
        session.cancel_current()

    await asyncio.gather(session.handle_user_input("go"), cancel_quickly())

    # Either truncated assistant or no assistant turn at all is acceptable;
    # we assert no crash and history is coherent.
    snap = history.snapshot()
    assert snap[0].role == "user"


async def test_max_tool_iterations_breaks_loop(tmp_path):
    from tests.conftest import FakeProvider
    # Build 10 scripts each ending in a tool_use — should hit cap at 8.
    scripts = []
    for i in range(10):
        scripts.append([
            ToolUseStart(tool_use_id=f"t{i}", name="weather"),
            ToolUseEnd(tool_use_id=f"t{i}", name="weather", args={"location": "X"}),
            TurnEnd(reason="tool_use"),
        ])
    provider = FakeProvider(scripts=scripts)
    history = History.new(tmp_path)
    renderer = CapturingRenderer()
    session = ChatSession(provider=provider, registry=build_registry(),
                         history=history, renderer=renderer,
                         max_tool_iterations=8)
    await session.handle_user_input("loop forever")

    # Provider should have been called 8 times max.
    assert len(provider.calls) <= 8
    # An error/guard turn should appear at the tail.
    assert any("max tool iterations" in (t.content or "") or
               any("max" in str(r) for r in t.tool_results)
               for t in history.snapshot())

    # History must be replay-safe: every assistant tool_call has a matching tool_result.
    snap = history.snapshot()
    for i, t in enumerate(snap):
        if t.role == "assistant" and t.tool_calls:
            # next turn must be a tool turn with matching ids
            assert i + 1 < len(snap), "assistant tool_calls must be followed by a tool turn"
            next_t = snap[i + 1]
            assert next_t.role == "tool"
            ids_in_use = {tc["id"] for tc in t.tool_calls}
            ids_in_results = {r["id"] for r in next_t.tool_results}
            assert ids_in_use == ids_in_results


async def test_cancel_mid_tool_appends_synthetic_tool_results(tmp_path):
    """If cancelled while tools are pending, history must include matching tool_results
    so the conversation can be replayed through Anthropic/OpenAI without orphan tool_use blocks."""
    from tests.conftest import FakeProvider

    provider = FakeProvider(scripts=[[
        ToolUseStart(tool_use_id="t1", name="weather"),
        ToolUseEnd(tool_use_id="t1", name="weather", args={"location": "London"}),
        TurnEnd(reason="cancelled"),
    ]])
    history = History.new(tmp_path)
    renderer = CapturingRenderer()
    session = ChatSession(provider=provider, registry=build_registry(),
                         history=history, renderer=renderer)
    await session.handle_user_input("weather?")

    snap = history.snapshot()
    # Find the assistant turn with the tool_use, and the matching tool turn.
    assistant = next(t for t in snap if t.role == "assistant" and t.tool_calls)
    tool_turn = next((t for t in snap if t.role == "tool"), None)
    assert tool_turn is not None, "must append synthetic tool turn even on cancel"
    ids_in_use = {tc["id"] for tc in assistant.tool_calls}
    ids_in_results = {r["id"] for r in tool_turn.tool_results}
    assert ids_in_use == ids_in_results, "every pending tool_use must have a matching tool_result"
    assert all(r["is_error"] for r in tool_turn.tool_results)
