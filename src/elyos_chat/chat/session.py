"""ChatSession — orchestrates a turn from user input to final assistant reply.

Owns the per-turn CancelToken; loops over the provider until either a stop
reason or MAX_TOOL_ITERATIONS is reached. Tool calls run in parallel.
"""
from __future__ import annotations
import asyncio
from typing import Protocol

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.chat.events import (
    Error, Event, TextDelta, ToolUseArgsDelta, ToolUseEnd, ToolUseStart, TurnEnd,
)
from elyos_chat.chat.history import History, Turn

MAX_TOOL_ITERATIONS = 8


class Renderer(Protocol):
    def write(self, text: str) -> None: ...
    def begin_tool(self, name: str) -> None: ...
    def end_tool(self, name: str, result: dict) -> None: ...
    def show_error(self, msg: str) -> None: ...
    def turn_done(self) -> None: ...


class ChatSession:
    def __init__(
        self,
        provider,
        registry,
        history: History,
        renderer: Renderer,
        system: str | None = None,
        max_tool_iterations: int = MAX_TOOL_ITERATIONS,
    ):
        self.provider = provider
        self.registry = registry
        self.history = history
        self.renderer = renderer
        self.system = system
        self.max_tool_iterations = max_tool_iterations
        self._cancel: CancelToken | None = None

    def cancel_current(self) -> None:
        if self._cancel is not None:
            self._cancel.cancel()

    async def handle_user_input(self, text: str) -> None:
        self.history.append(Turn(role="user", content=text))
        cancel = CancelToken()
        self._cancel = cancel
        try:
            await self._run_loop(cancel)
        finally:
            self._cancel = None
            self.renderer.turn_done()

    async def _run_loop(self, cancel: CancelToken) -> None:
        tools_for_provider = self._tools_for_provider()
        for iteration in range(self.max_tool_iterations):
            assistant_text_parts: list[str] = []
            pending_tools: list[dict] = []
            tool_names_seen: dict[str, str] = {}
            cancelled = False

            async for ev in self.provider.stream_turn(
                self.history.snapshot(), tools_for_provider, cancel, system=self.system,
            ):
                if isinstance(ev, TextDelta):
                    assistant_text_parts.append(ev.text)
                    self.renderer.write(ev.text)
                elif isinstance(ev, ToolUseStart):
                    tool_names_seen[ev.tool_use_id] = ev.name
                    self.renderer.begin_tool(ev.name)
                elif isinstance(ev, ToolUseArgsDelta):
                    pass  # we use the parsed args from ToolUseEnd
                elif isinstance(ev, ToolUseEnd):
                    pending_tools.append({"id": ev.tool_use_id, "name": ev.name, "args": ev.args})
                elif isinstance(ev, Error):
                    self.renderer.show_error(ev.message)
                elif isinstance(ev, TurnEnd):
                    if ev.reason == "cancelled":
                        cancelled = True
                    break

            assistant_content = "".join(assistant_text_parts)
            self.history.append(Turn(
                role="assistant",
                content=assistant_content,
                tool_calls=pending_tools,
                cancelled=cancelled,
            ))

            if cancelled:
                if pending_tools:
                    self.history.append(Turn(
                        role="tool",
                        tool_results=[
                            {"id": tc["id"], "name": tc["name"],
                             "content": {"error": "cancelled by user"}, "is_error": True}
                            for tc in pending_tools
                        ],
                    ))
                return
            if not pending_tools:
                return

            # Dispatch tools in parallel.
            results = await asyncio.gather(
                *[self.registry.dispatch(tc["name"], tc["args"], cancel) for tc in pending_tools],
                return_exceptions=True,
            )
            tool_results = []
            for tc, res in zip(pending_tools, results):
                if isinstance(res, Exception):
                    content = {"error": f"{type(res).__name__}: {res}"}
                    is_error = True
                else:
                    content = res
                    is_error = bool(res.get("error"))
                tool_results.append({
                    "id": tc["id"],
                    "name": tc["name"],
                    "content": content,
                    "is_error": is_error,
                })
                self.renderer.end_tool(tc["name"], content)

            self.history.append(Turn(role="tool", tool_results=tool_results))

            if cancel.cancelled():
                return

        # Max iterations hit. The most recent assistant turn may have pending
        # tool_use blocks that need matching tool_result entries for history
        # coherence (otherwise Anthropic/OpenAI reject the replay).
        self.renderer.show_error(f"max tool iterations reached ({self.max_tool_iterations})")
        snap = self.history.snapshot()
        last_tool_calls = []
        for t in reversed(snap):
            if t.role == "assistant":
                last_tool_calls = list(t.tool_calls)
                break
        if last_tool_calls:
            self.history.append(Turn(
                role="tool",
                tool_results=[
                    {"id": tc["id"], "name": tc["name"],
                     "content": {"error": "max tool iterations exceeded"}, "is_error": True}
                    for tc in last_tool_calls
                ],
            ))

    def _tools_for_provider(self) -> list[dict]:
        name = self.provider.name
        if name == "anthropic":
            return self.registry.for_anthropic()
        if name == "openai":
            return self.registry.for_openai()
        if name == "gemini":
            return self.registry.for_gemini()
        return []  # FakeProvider in tests doesn't use tool schemas
