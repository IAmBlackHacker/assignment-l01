"""/ws/voice — voice-mode relay.

Pumps audio + JSON between the browser and OpenAI Realtime. Translates
Realtime events into canonical JSON for the client. Dispatches tool calls
through the shared ToolRegistry (same handlers as text mode, including
all 8 quirk handlers F-01..F-08).
"""
from __future__ import annotations
import asyncio
import base64
import json
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.chat.history import History, Turn
from web.deps import HISTORY_DIR, state
from web.realtime import OpenAIRealtimeWS, RealtimeWS

router = APIRouter()


async def connect_realtime(voice: str, tools: list[dict]) -> RealtimeWS:
    """Indirection so tests can monkeypatch."""
    return await OpenAIRealtimeWS.connect(voice=voice, tools=tools)


@router.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    await ws.accept()
    upstream: Optional[RealtimeWS] = None
    history: Optional[History] = None
    cancel = CancelToken()
    assistant_buf: list[str] = []

    try:
        hello = await ws.receive_json()
        if hello.get("type") != "hello":
            await ws.send_json({"type": "error", "message": "expected hello"})
            await ws.close()
            return

        sid = hello.get("session_id", "new")
        voice = hello.get("voice", "alloy")
        if sid == "new":
            history = History.new(HISTORY_DIR)
        elif sid == "last":
            history = History.resume_last(HISTORY_DIR) or History.new(HISTORY_DIR)
        else:
            history = History.resume(HISTORY_DIR, sid)

        tools_for_realtime = state.registry.for_openai() if state.registry else []
        # Realtime expects flat function declarations, not wrapped in type:function.
        tools_for_realtime = [t["function"] for t in tools_for_realtime] if tools_for_realtime else []

        upstream = await connect_realtime(voice, tools_for_realtime)
        await ws.send_json({"type": "session_started", "session_id": history.session_id})

        client_task = asyncio.create_task(_client_pump(ws, upstream, cancel))
        upstream_task = asyncio.create_task(
            _upstream_pump(ws, upstream, cancel, history, assistant_buf)
        )

        done, pending = await asyncio.wait(
            {client_task, upstream_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "message": f"{type(e).__name__}: {e}"})
        except Exception:
            pass
    finally:
        if upstream:
            try:
                await upstream.close()
            except Exception:
                pass


async def _client_pump(ws: WebSocket, upstream: RealtimeWS, cancel: CancelToken):
    while True:
        msg = await ws.receive()
        if msg["type"] == "websocket.disconnect":
            return
        if msg.get("bytes") is not None:
            # Always send audio as JSON envelope so FakeRealtimeWS (and real
            # OpenAIRealtimeWS) sees input_audio_buffer.append in sent_json.
            await upstream.send_json({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(msg["bytes"]).decode("ascii"),
            })
        elif msg.get("text") is not None:
            try:
                obj = json.loads(msg["text"])
            except ValueError:
                continue
            t = obj.get("type")
            if t == "cancel":
                cancel.cancel()
                await upstream.send_json({"type": "response.cancel"})
            elif t == "stop":
                return


async def _upstream_pump(
    ws: WebSocket,
    upstream: RealtimeWS,
    cancel: CancelToken,
    history: History,
    assistant_buf: list[str],
):
    while True:
        ev = await upstream.recv()
        if isinstance(ev, bytes):
            await ws.send_bytes(ev)
            continue
        t = ev.get("type", "")
        if t == "input_audio_buffer.speech_started":
            await ws.send_json({"type": "speech_started"})
        elif t == "input_audio_buffer.speech_stopped":
            await ws.send_json({"type": "speech_stopped"})
        elif t == "response.audio.delta":
            pcm = base64.b64decode(ev["delta"])
            await ws.send_bytes(pcm)
        elif t == "response.audio_transcript.delta":
            assistant_buf.append(ev.get("delta", ""))
            await ws.send_json({"type": "transcript_assistant_delta", "text": ev.get("delta", "")})
        elif t == "response.audio_transcript.done":
            final = ev.get("transcript", "")
            # If deltas arrived, assistant_buf already has the full text.
            # If not (e.g., Realtime only sent the done event), use the final
            # transcript directly so response.done has something to persist.
            if not assistant_buf and final:
                assistant_buf.append(final)
            await ws.send_json({"type": "transcript_assistant_done", "text": final})
        elif t == "conversation.item.input_audio_transcription.completed":
            text = ev.get("transcript", "")
            await ws.send_json({"type": "transcript_user_done", "text": text})
            history.append(Turn(role="user", content=text, ts=time.time()))
            _stamp_voice_on_last(history, "user")
        elif t == "response.function_call_arguments.done":
            await _handle_tool_call(ev, ws, upstream, cancel)
        elif t == "response.done":
            text = "".join(assistant_buf)
            assistant_buf.clear()
            if text:
                history.append(Turn(role="assistant", content=text, ts=time.time()))
                _stamp_voice_on_last(history, "assistant")
            await ws.send_json({"type": "turn_end", "reason": "stop"})
        elif t == "error":
            await ws.send_json({"type": "error", "message": ev.get("error", {}).get("message", "realtime error")})


def _stamp_voice_on_last(history: History, role: str) -> None:
    """Append a 'voice': true flag to the most recent JSONL line of `role`.

    Turn doesn't currently carry a voice field; we rewrite the last line.
    """
    path = history.path
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    for i in range(len(lines) - 1, -1, -1):
        try:
            obj = json.loads(lines[i])
        except ValueError:
            continue
        if obj.get("role") == role:
            obj["voice"] = True
            lines[i] = json.dumps(obj, ensure_ascii=False)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return


async def _handle_tool_call(ev: dict, ws: WebSocket, upstream: RealtimeWS, cancel: CancelToken):
    name = ev["name"]
    call_id = ev["call_id"]
    args = json.loads(ev.get("arguments", "{}") or "{}")

    await ws.send_json({"type": "tool_use_start", "id": call_id, "name": name})
    await ws.send_json({"type": "tool_use_end", "id": call_id, "name": name, "args": args})

    if state.registry is None:
        result = {"error": "registry not initialised"}
    else:
        result = await state.registry.dispatch(name, args, cancel)
    is_error = bool(result.get("error"))

    await ws.send_json({"type": "tool_result", "id": call_id, "name": name,
                        "content": result, "is_error": is_error})

    await upstream.send_json({
        "type": "conversation.item.create",
        "item": {"type": "function_call_output", "call_id": call_id,
                 "output": json.dumps(result)},
    })
    await upstream.send_json({"type": "response.create"})
