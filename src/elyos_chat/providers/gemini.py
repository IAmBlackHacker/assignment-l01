"""Gemini adapter — google-genai with streaming + function calling.

Gemini delivers tool args atomically (not as JSON fragments). For canonical
event-shape parity, we emit one synthetic ToolUseArgsDelta containing the
full JSON, then ToolUseEnd.
"""
from __future__ import annotations
import asyncio
import json
import os
from typing import AsyncIterator

from google import genai
from google.genai import types as gtypes

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.chat.events import (
    Error, Event, TextDelta, ToolUseArgsDelta, ToolUseEnd, ToolUseStart, TurnEnd,
)
from elyos_chat.chat.history import Turn

DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str | None = None):
        self.model = model or DEFAULT_MODEL
        self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    async def stream_turn(self, turns, tools, cancel, system=None) -> AsyncIterator[Event]:
        contents = self._to_contents(turns)
        config = gtypes.GenerateContentConfig(
            tools=[gtypes.Tool(function_declarations=tools)] if tools else None,
            system_instruction=system,
        )
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config,
            )
            stop_reason = "stop"
            tool_idx = 0
            async for chunk in stream:
                if cancel.cancelled():
                    yield TurnEnd(reason="cancelled")
                    return
                for cand in (chunk.candidates or []):
                    if not cand.content or not cand.content.parts:
                        continue
                    for part in cand.content.parts:
                        if getattr(part, "text", None):
                            yield TextDelta(text=part.text)
                        if getattr(part, "function_call", None):
                            fc = part.function_call
                            tool_id = f"gemini-tc-{tool_idx}"
                            tool_idx += 1
                            yield ToolUseStart(tool_use_id=tool_id, name=fc.name)
                            args_json = json.dumps(dict(fc.args or {}))
                            yield ToolUseArgsDelta(tool_use_id=tool_id, partial_json=args_json)
                            yield ToolUseEnd(tool_use_id=tool_id, name=fc.name, args=dict(fc.args or {}))
                            stop_reason = "tool_use"
                    if getattr(cand, "finish_reason", None) and stop_reason != "tool_use":
                        stop_reason = "stop"
            yield TurnEnd(reason=stop_reason)
        except asyncio.CancelledError:
            yield TurnEnd(reason="cancelled")
        except Exception as e:
            yield Error(message=f"gemini: {type(e).__name__}: {e}", transient=True)
            yield TurnEnd(reason="error")

    def _to_contents(self, turns: list[Turn]) -> list[gtypes.Content]:
        contents = []
        for t in turns:
            if t.role == "user":
                contents.append(gtypes.Content(role="user", parts=[gtypes.Part.from_text(text=t.content)]))
            elif t.role == "assistant":
                parts = []
                if t.content:
                    parts.append(gtypes.Part.from_text(text=t.content))
                for tc in t.tool_calls:
                    parts.append(gtypes.Part.from_function_call(name=tc["name"], args=tc["args"]))
                if parts:
                    contents.append(gtypes.Content(role="model", parts=parts))
            elif t.role == "tool":
                parts = [
                    gtypes.Part.from_function_response(
                        name=r.get("name", "unknown"),
                        response=r["content"] if isinstance(r["content"], dict) else {"result": r["content"]},
                    )
                    for r in t.tool_results
                ]
                contents.append(gtypes.Content(role="user", parts=parts))
        return contents
