"""/ws/text — text-mode WebSocket handler.

Translates client JSON messages into ChatSession operations, and translates
ChatSession's canonical Events into JSON for the client.
"""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from elyos_chat.chat.events import (
    Error, Event, TextDelta, ToolUseArgsDelta, ToolUseEnd, ToolUseStart, TurnEnd,
)
from elyos_chat.chat.history import History, Turn
from elyos_chat.chat.session import ChatSession
from elyos_chat.chat.cancel import CancelToken
from web.deps import HISTORY_DIR, state

router = APIRouter()


def _history_to_messages(history: History) -> list[dict]:
    """Convert persisted turns to the UI's Message shape.

    Reads the raw JSONL so voice=true stamps (added by ws_voice.py via direct
    file rewrite, not via the Turn dataclass) survive resume.
    """
    out: list[dict] = []
    path = history.path
    if not path.exists():
        return out
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            t = json.loads(line)
        except ValueError:
            continue
        role = t.get("role")
        ts = t.get("ts", i)
        if role == "user":
            out.append({
                "id": f"u-{i}-{ts}",
                "role": "user",
                "content": t.get("content", ""),
                "voice": bool(t.get("voice")),
            })
        elif role == "assistant":
            # Skip pure tool-call assistant turns (no text content) — the tool
            # row in the next tool turn renders the visible state.
            content = t.get("content", "")
            if content:
                out.append({
                    "id": f"a-{i}-{ts}",
                    "role": "assistant",
                    "content": content,
                    "voice": bool(t.get("voice")),
                    "cancelled": bool(t.get("cancelled")),
                })
        elif role == "tool":
            out.append({
                "id": f"t-{i}-{ts}",
                "role": "tool",
                "content": "",
                "toolResults": [
                    {
                        "id": r.get("id", ""),
                        "name": r.get("name", ""),
                        "content": r.get("content", {}),
                        "isError": bool(r.get("is_error")),
                    }
                    for r in t.get("tool_results", [])
                ],
            })
    return out


def build_provider(provider_name: str, model: Optional[str]):
    """Construct a real provider. Tests monkeypatch this to inject a FakeProvider."""
    if provider_name == "anthropic":
        from elyos_chat.providers.anthropic import AnthropicProvider
        return AnthropicProvider(model=model)
    if provider_name == "openai":
        from elyos_chat.providers.openai import OpenAIProvider
        return OpenAIProvider(model=model)
    if provider_name == "gemini":
        from elyos_chat.providers.gemini import GeminiProvider
        return GeminiProvider(model=model)
    raise ValueError(f"unsupported provider: {provider_name}")


class WSRenderer:
    """Adapts ChatSession's Renderer Protocol into events on an asyncio.Queue.

    ChatSession's renderer methods are synchronous; we put_nowait onto a
    queue that the WS sender drains and forwards as JSON.
    """
    def __init__(self, queue: asyncio.Queue):
        self._q = queue

    def write(self, text: str):
        self._q.put_nowait({"type": "text_delta", "text": text})

    def begin_tool(self, name: str):
        pass  # tool_use_start emitted from history tail after handle_user_input

    def end_tool(self, name: str, result: dict):
        pass  # tool_result emitted from history tail after handle_user_input

    def show_error(self, msg: str):
        self._q.put_nowait({"type": "error", "message": msg, "transient": False})

    def turn_done(self):
        pass


@router.websocket("/ws/text")
async def ws_text(ws: WebSocket):
    await ws.accept()
    history: Optional[History] = None
    settings = {"provider": "anthropic", "model": None, "system": None}
    current_session: Optional[ChatSession] = None
    current_task: Optional[asyncio.Task] = None

    try:
        hello = await ws.receive_json()
        if hello.get("type") != "hello":
            await ws.send_json({"type": "error", "message": "expected hello", "transient": False})
            await ws.close()
            return

        sid = hello.get("session_id", "new")
        if sid == "new":
            history = History.new(HISTORY_DIR)
            created = True
            resumed = 0
        elif sid == "last":
            history = History.resume_last(HISTORY_DIR) or History.new(HISTORY_DIR)
            resumed = len(history.snapshot())
            created = resumed == 0
        else:
            history = History.resume(HISTORY_DIR, sid)
            created = False
            resumed = len(history.snapshot())

        settings["provider"] = hello.get("provider", "anthropic")
        settings["model"] = hello.get("model")
        settings["system"] = hello.get("system")

        await ws.send_json({
            "type": "session_started",
            "session_id": history.session_id,
            "created": created,
            "resumed_turns": resumed,
            "messages": _history_to_messages(history),
        })

        while True:
            msg = await ws.receive_json()
            t = msg.get("type")
            if t == "user":
                if current_task and not current_task.done():
                    await ws.send_json({"type": "error", "message": "turn already in flight", "transient": True})
                    continue
                provider = build_provider(settings["provider"], settings["model"])
                queue: asyncio.Queue = asyncio.Queue()
                current_session = ChatSession(
                    provider=provider,
                    registry=state.registry,
                    history=history,
                    renderer=WSRenderer(queue),
                    system=settings["system"],
                )
                user_text = msg.get("content", "")
                await ws.send_json({"type": "user_echo", "content": user_text})
                current_task = asyncio.create_task(_run_turn(current_session, user_text, queue, ws))
            elif t == "cancel":
                if current_session:
                    current_session.cancel_current()
            elif t == "update_settings":
                for k in ("provider", "model", "system"):
                    if k in msg:
                        settings[k] = msg[k]
            else:
                await ws.send_json({"type": "error", "message": f"unknown type: {t}", "transient": False})

    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "message": f"{type(e).__name__}: {e}", "transient": False})
        except Exception:
            pass


async def _run_turn(session: ChatSession, user_text: str, queue: asyncio.Queue, ws: WebSocket):
    """Run a turn and stream events to the WS.

    Strategy: snapshot history length before, run handle_user_input, then
    emit tool_use_start/end/result for any new tool turns added during the
    call. Text deltas reach the WS via the renderer queue concurrently.
    """
    drainer = asyncio.create_task(_drain_queue(queue, ws))
    pre_len = len(session.history.snapshot())
    try:
        await session.handle_user_input(user_text)
        # Cancel the drainer and flush any remaining items from the queue
        # directly so all text_deltas arrive before tool events / turn_end.
        drainer.cancel()
        try:
            await drainer
        except asyncio.CancelledError:
            pass
        # Drain whatever is still in the queue (drainer may not have run all items).
        while not queue.empty():
            msg = queue.get_nowait()
            await ws.send_json(msg)
        # Emit tool events from any new turns.
        new_turns = session.history.snapshot()[pre_len:]
        for turn in new_turns:
            if turn.role == "assistant":
                for tc in turn.tool_calls:
                    await ws.send_json({"type": "tool_use_start", "id": tc["id"], "name": tc["name"]})
                    await ws.send_json({"type": "tool_use_end", "id": tc["id"], "name": tc["name"], "args": tc["args"]})
            elif turn.role == "tool":
                for r in turn.tool_results:
                    await ws.send_json({"type": "tool_result", "id": r["id"], "name": r["name"],
                                        "content": r["content"], "is_error": r["is_error"]})
        reason = "stop"
        snap = session.history.snapshot()
        if snap:
            last = snap[-1]
            if last.role == "assistant" and last.cancelled:
                reason = "cancelled"
        await ws.send_json({"type": "turn_end", "reason": reason})
    except Exception:
        drainer.cancel()
        raise


async def _drain_queue(queue: asyncio.Queue, ws: WebSocket):
    while True:
        msg = await queue.get()
        await ws.send_json(msg)
