"""Voice relay translation tests.

Uses a FakeRealtimeWS that lets tests script upstream events and observe
the messages the relay sends upstream. Browser side uses TestClient.
"""
import asyncio
import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.server import app
from web import deps, ws_voice


class FakeRealtimeWS:
    def __init__(self, scripted_events=None):
        self.sent_json: list[dict] = []
        self.sent_bytes: list[bytes] = []
        self.scripted: list = list(scripted_events or [])
        self._recv_queue: asyncio.Queue = asyncio.Queue()
        for ev in self.scripted:
            self._recv_queue.put_nowait(ev)
        self.closed = False

    async def send_json(self, msg):
        self.sent_json.append(msg)

    async def send_bytes(self, data):
        self.sent_bytes.append(data)

    async def recv(self):
        return await self._recv_queue.get()

    async def close(self):
        self.closed = True


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(deps, "HISTORY_DIR", tmp_path)
    monkeypatch.setattr(ws_voice, "HISTORY_DIR", tmp_path)
    return TestClient(app), tmp_path


def test_audio_binary_passthrough(client, monkeypatch):
    c, _ = client
    fake = FakeRealtimeWS()

    async def fake_connect(voice, tools):
        return fake
    monkeypatch.setattr(ws_voice, "connect_realtime", fake_connect)

    with c.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "hello", "session_id": "new", "voice": "alloy"})
        ws.receive_json()
        ws.send_bytes(b"\x01\x02\x03\x04")
        import time; time.sleep(0.1)
        # Audio sent upstream as base64 inside JSON envelope.
        assert any(m.get("type") == "input_audio_buffer.append" for m in fake.sent_json)


def test_transcript_delta_maps_to_client_event(client, monkeypatch):
    c, _ = client
    fake = FakeRealtimeWS(scripted_events=[
        {"type": "response.audio_transcript.delta", "delta": "hello"},
    ])
    async def fake_connect(voice, tools): return fake
    monkeypatch.setattr(ws_voice, "connect_realtime", fake_connect)

    with c.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "hello", "session_id": "new"})
        ws.receive_json()
        for _ in range(10):
            m = ws.receive_json()
            if m["type"] == "transcript_assistant_delta":
                assert m["text"] == "hello"
                return
        pytest.fail("did not receive transcript_assistant_delta")


def test_assistant_audio_forwarded(client, monkeypatch):
    c, _ = client
    pcm = b"\x10\x20\x30\x40"
    fake = FakeRealtimeWS(scripted_events=[
        {"type": "response.audio.delta", "delta": base64.b64encode(pcm).decode("ascii")},
    ])
    async def fake_connect(voice, tools): return fake
    monkeypatch.setattr(ws_voice, "connect_realtime", fake_connect)

    with c.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "hello", "session_id": "new"})
        ws.receive_json()
        for _ in range(10):
            data = ws.receive()
            if "bytes" in data and data["bytes"]:
                assert data["bytes"] == pcm
                return
        pytest.fail("did not receive audio bytes")


def test_tool_call_dispatches_and_responds_upstream(client, monkeypatch):
    c, _ = client
    fake = FakeRealtimeWS(scripted_events=[
        {"type": "response.function_call_arguments.done",
         "call_id": "c1", "name": "weather",
         "arguments": json.dumps({"location": "London"})},
    ])
    async def fake_connect(voice, tools): return fake
    monkeypatch.setattr(ws_voice, "connect_realtime", fake_connect)

    async def stub_dispatch(name, args, cancel):
        return {"temp_c": 12}
    monkeypatch.setattr(deps.state.registry, "dispatch", stub_dispatch)

    with c.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "hello", "session_id": "new"})
        ws.receive_json()
        seen = []
        for _ in range(15):
            try:
                data = ws.receive()
                if "text" in data and data["text"]:
                    m = json.loads(data["text"])
                    seen.append(m)
                    if m["type"] == "tool_result":
                        break
            except Exception:
                continue
        types = [m["type"] for m in seen]
        assert "tool_use_start" in types
        assert "tool_use_end" in types
        assert "tool_result" in types
        upstream_types = [m["type"] for m in fake.sent_json]
        assert "conversation.item.create" in upstream_types
        assert "response.create" in upstream_types


def test_cancel_propagates_upstream(client, monkeypatch):
    c, _ = client
    fake = FakeRealtimeWS()
    async def fake_connect(voice, tools): return fake
    monkeypatch.setattr(ws_voice, "connect_realtime", fake_connect)

    with c.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "hello", "session_id": "new"})
        ws.receive_json()
        ws.send_json({"type": "cancel"})
        import time; time.sleep(0.2)
        assert any(m.get("type") == "response.cancel" for m in fake.sent_json)


def test_voice_transcript_persists_to_jsonl(client, monkeypatch, tmp_path):
    c, d = client
    fake = FakeRealtimeWS(scripted_events=[
        {"type": "conversation.item.input_audio_transcription.completed",
         "transcript": "hello"},
        {"type": "response.audio_transcript.done", "transcript": "hi there"},
        {"type": "response.done"},
    ])
    async def fake_connect(voice, tools): return fake
    monkeypatch.setattr(ws_voice, "connect_realtime", fake_connect)

    with c.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "hello", "session_id": "new"})
        started = ws.receive_json()
        sid = started["session_id"]
        for _ in range(15):
            try:
                data = ws.receive()
                if "text" in data and data["text"]:
                    m = json.loads(data["text"])
                    if m.get("type") == "turn_end":
                        break
            except Exception:
                continue

    path = d / f"{sid}.jsonl"
    assert path.exists()
    lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    roles = [l["role"] for l in lines]
    assert "user" in roles
    assert "assistant" in roles
    assert all(l.get("voice") for l in lines)
