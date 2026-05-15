"""OpenAI adapter — chat.completions streaming with tool calls."""
from __future__ import annotations
import asyncio
import json
import os
from typing import AsyncIterator

from openai import AsyncOpenAI

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.chat.events import (
    Error, Event, TextDelta, ToolUseArgsDelta, ToolUseEnd, ToolUseStart, TurnEnd,
)
from elyos_chat.chat.history import Turn

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str | None = None):
        self.model = model or DEFAULT_MODEL
        self._client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    async def stream_turn(self, turns, tools, cancel, system=None) -> AsyncIterator[Event]:
        messages = self._to_messages(turns, system)
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                stream=True,
            )
            pending: dict[int, dict] = {}  # tool_call index → {"id", "name", "args": []}
            announced: set[int] = set()
            stop_reason = "stop"
            async for chunk in stream:
                if cancel.cancelled():
                    await stream.close()
                    yield TurnEnd(reason="cancelled")
                    return
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta.content:
                    yield TextDelta(text=delta.content)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        slot = pending.setdefault(idx, {"id": None, "name": None, "args": []})
                        if tc.id:
                            slot["id"] = tc.id
                        if tc.function and tc.function.name:
                            slot["name"] = tc.function.name
                        if idx not in announced and slot["id"] and slot["name"]:
                            announced.add(idx)
                            yield ToolUseStart(tool_use_id=slot["id"], name=slot["name"])
                        if tc.function and tc.function.arguments:
                            slot["args"].append(tc.function.arguments)
                            if slot["id"]:
                                yield ToolUseArgsDelta(
                                    tool_use_id=slot["id"],
                                    partial_json=tc.function.arguments,
                                )
                if choice.finish_reason:
                    stop_reason = choice.finish_reason
            # Emit ToolUseEnd for each pending tool, then TurnEnd.
            for slot in pending.values():
                args_text = "".join(slot["args"])
                try:
                    args = json.loads(args_text) if args_text else {}
                except json.JSONDecodeError:
                    args = {"_raw": args_text}
                yield ToolUseEnd(tool_use_id=slot["id"], name=slot["name"], args=args)
            reason = "tool_use" if stop_reason == "tool_calls" else "stop"
            yield TurnEnd(reason=reason)
        except asyncio.CancelledError:
            yield TurnEnd(reason="cancelled")
        except Exception as e:
            yield Error(message=f"openai: {type(e).__name__}: {e}", transient=True)
            yield TurnEnd(reason="error")

    def _to_messages(self, turns: list[Turn], system: str | None) -> list[dict]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        for t in turns:
            if t.role == "user":
                msgs.append({"role": "user", "content": t.content})
            elif t.role == "assistant":
                # Skip assistant turns with no content AND no tool_calls.
                # These arise from failed/errored turns (e.g. provider auth
                # error); OpenAI rejects messages with content=null and no
                # tool_calls.
                if not t.content and not t.tool_calls:
                    continue
                m = {"role": "assistant", "content": t.content or None}
                if t.tool_calls:
                    m["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"]),
                            },
                        }
                        for tc in t.tool_calls
                    ]
                msgs.append(m)
            elif t.role == "tool":
                for r in t.tool_results:
                    msgs.append({
                        "role": "tool",
                        "tool_call_id": r["id"],
                        "content": json.dumps(r["content"]),
                    })
        return msgs
