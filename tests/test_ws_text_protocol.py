"""WebSocket protocol contract tests for /ws/text.

Uses a FakeProvider scripted with canonical Events to drive ChatSession,
and asserts the JSON shape arriving at the WS client.
"""
import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from elyos_chat.chat.events import TextDelta, ToolUseEnd, ToolUseStart, TurnEnd
from web.server import app
from web import deps, ws_text


class FakeProvider:
    name = "fake"
    model = "fake-1"

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.calls = []

    async def stream_turn(self, turns, tools, cancel, system=None):
        self.calls.append({"turns": list(turns)})
        if not self.scripts:
            return
        events = self.scripts.pop(0)
        for ev in events:
            if cancel.cancelled():
                return
            yield ev


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(deps, "HISTORY_DIR", tmp_path)
    monkeypatch.setattr(ws_text, "HISTORY_DIR", tmp_path)
    yield TestClient(app), tmp_path


def test_hello_starts_new_session(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(ws_text, "build_provider", lambda *_a, **_kw: FakeProvider([]))
    with c.websocket_connect("/ws/text") as ws:
        ws.send_json({"type": "hello", "session_id": "new", "provider": "fake"})
        msg = ws.receive_json()
        assert msg["type"] == "session_started"
        assert msg["created"] is True
        assert msg["session_id"]


def test_user_message_streams_tokens(client, monkeypatch):
    c, _ = client
    provider = FakeProvider([[TextDelta("hello"), TextDelta(" world"), TurnEnd(reason="stop")]])
    monkeypatch.setattr(ws_text, "build_provider", lambda *_a, **_kw: provider)
    with c.websocket_connect("/ws/text") as ws:
        ws.send_json({"type": "hello", "session_id": "new", "provider": "fake"})
        ws.receive_json()
        ws.send_json({"type": "user", "content": "hi"})
        types = []
        for _ in range(20):
            m = ws.receive_json()
            types.append(m["type"])
            if m["type"] == "turn_end":
                break
        assert "user_echo" in types
        assert types.count("text_delta") == 2
        assert types[-1] == "turn_end"


def test_tool_call_emits_canonical_events(client, monkeypatch):
    c, _ = client
    provider = FakeProvider([
        [
            ToolUseStart(tool_use_id="t1", name="weather"),
            ToolUseEnd(tool_use_id="t1", name="weather", args={"location": "London"}),
            TurnEnd(reason="tool_use"),
        ],
        [TextDelta("done"), TurnEnd(reason="stop")],
    ])
    monkeypatch.setattr(ws_text, "build_provider", lambda *_a, **_kw: provider)

    async def stub_dispatch(name, args, cancel):
        return {"temp_c": 12, "echo": args}
    monkeypatch.setattr(deps.state.registry, "dispatch", stub_dispatch)

    with c.websocket_connect("/ws/text") as ws:
        ws.send_json({"type": "hello", "session_id": "new", "provider": "fake"})
        ws.receive_json()
        ws.send_json({"type": "user", "content": "weather in London"})
        captured = []
        for _ in range(50):
            m = ws.receive_json()
            captured.append(m)
            if m["type"] == "turn_end" and m["reason"] == "stop":
                break
        types = [m["type"] for m in captured]
        assert "tool_use_start" in types
        assert "tool_result" in types
        tool_result = next(m for m in captured if m["type"] == "tool_result")
        assert tool_result["content"]["temp_c"] == 12
        assert tool_result["is_error"] is False


def test_cancel_during_long_provider(client, monkeypatch):
    c, _ = client

    class SlowProvider:
        name = "fake"
        model = "fake-1"
        async def stream_turn(self, turns, tools, cancel, system=None):
            for i in range(50):
                if cancel.cancelled():
                    yield TurnEnd(reason="cancelled")
                    return
                await asyncio.sleep(0.01)
                yield TextDelta(text=f"x{i}")
            yield TurnEnd(reason="stop")

    monkeypatch.setattr(ws_text, "build_provider", lambda *_a, **_kw: SlowProvider())
    with c.websocket_connect("/ws/text") as ws:
        ws.send_json({"type": "hello", "session_id": "new", "provider": "fake"})
        ws.receive_json()
        ws.send_json({"type": "user", "content": "go"})
        for _ in range(3):
            ws.receive_json()
        ws.send_json({"type": "cancel"})
        end = None
        for _ in range(60):
            m = ws.receive_json()
            if m["type"] == "turn_end":
                end = m
                break
        assert end is not None
        assert end["reason"] == "cancelled"


def test_resume_replays_history(client, monkeypatch, tmp_path):
    c, d = client
    (d / "abc.jsonl").write_text(
        '{"role":"user","content":"earlier","ts":1.0}\n'
        '{"role":"assistant","content":"prior reply","ts":1.1}\n'
    )
    monkeypatch.setattr(ws_text, "build_provider", lambda *_a, **_kw: FakeProvider([]))
    with c.websocket_connect("/ws/text") as ws:
        ws.send_json({"type": "hello", "session_id": "abc", "provider": "fake"})
        m = ws.receive_json()
        assert m["type"] == "session_started"
        assert m["session_id"] == "abc"
        assert m["created"] is False
        assert m["resumed_turns"] == 2


def test_invalid_message_returns_error(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(ws_text, "build_provider", lambda *_a, **_kw: FakeProvider([]))
    with c.websocket_connect("/ws/text") as ws:
        ws.send_json({"type": "hello", "session_id": "new", "provider": "fake"})
        ws.receive_json()
        ws.send_json({"type": "garbage"})
        m = ws.receive_json()
        assert m["type"] == "error"
        assert m.get("transient") is False
