"""Anthropic adapter — Claude Messages API with streaming + tool use."""
from __future__ import annotations
import asyncio
import json
import os
from typing import AsyncIterator

from anthropic import AsyncAnthropic

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.chat.events import (
    Error, Event, TextDelta, ToolUseArgsDelta, ToolUseEnd, ToolUseStart, TurnEnd,
)
from elyos_chat.chat.history import Turn


DEFAULT_MODEL = "claude-sonnet-4-6"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str | None = None):
        self.model = model or DEFAULT_MODEL
        self._client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    async def stream_turn(
        self, turns, tools, cancel, system=None,
    ) -> AsyncIterator[Event]:
        messages = self._to_messages(turns)
        kwargs = dict(
            model=self.model,
            max_tokens=4096,
            messages=messages,
            tools=tools,
        )
        if system:
            kwargs["system"] = system

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                pending_args: dict[str, list[str]] = {}
                pending_meta: dict[str, dict] = {}
                async for event in stream:
                    if cancel.cancelled():
                        yield TurnEnd(reason="cancelled")
                        return
                    t = event.type
                    if t == "content_block_start":
                        block = event.content_block
                        if block.type == "tool_use":
                            pending_args[block.id] = []
                            pending_meta[block.id] = {"name": block.name}
                            yield ToolUseStart(tool_use_id=block.id, name=block.name)
                    elif t == "content_block_delta":
                        d = event.delta
                        if d.type == "text_delta":
                            yield TextDelta(text=d.text)
                        elif d.type == "input_json_delta":
                            # Anthropic's API attaches the tool_use_id via index;
                            # use the latest pending one (single tool at a time is typical).
                            tool_id = list(pending_args.keys())[-1] if pending_args else None
                            if tool_id is not None:
                                pending_args[tool_id].append(d.partial_json)
                                yield ToolUseArgsDelta(tool_use_id=tool_id, partial_json=d.partial_json)
                    elif t == "content_block_stop":
                        block = event.content_block
                        if block.type == "tool_use":
                            args_text = "".join(pending_args.pop(block.id, []))
                            try:
                                args = json.loads(args_text) if args_text else {}
                            except json.JSONDecodeError:
                                args = {"_raw": args_text}
                            yield ToolUseEnd(tool_use_id=block.id, name=block.name, args=args)
                    elif t == "message_stop":
                        msg = await stream.get_final_message()
                        reason = "tool_use" if msg.stop_reason == "tool_use" else "stop"
                        yield TurnEnd(reason=reason)
                        return
        except asyncio.CancelledError:
            yield TurnEnd(reason="cancelled")
        except Exception as e:
            yield Error(message=f"anthropic: {type(e).__name__}: {e}", transient=True)
            yield TurnEnd(reason="error")

    def _to_messages(self, turns: list[Turn]) -> list[dict]:
        msgs = []
        for t in turns:
            if t.role == "user":
                msgs.append({"role": "user", "content": t.content})
            elif t.role == "assistant":
                blocks = []
                if t.content:
                    blocks.append({"type": "text", "text": t.content})
                for tc in t.tool_calls:
                    blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc["args"],
                    })
                msgs.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
            elif t.role == "tool":
                blocks = [
                    {
                        "type": "tool_result",
                        "tool_use_id": r["id"],
                        "content": json.dumps(r["content"]),
                        "is_error": r.get("is_error", False),
                    }
                    for r in t.tool_results
                ]
                msgs.append({"role": "user", "content": blocks})
        return msgs
