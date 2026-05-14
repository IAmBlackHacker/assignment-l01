"""Tool registry: canonical JSON Schema per tool + per-provider translation.

Each tool has ONE canonical schema. Provider-specific tool definitions are
derived at call time. Adding a tool = define schema + register handler.
Adding a provider = add a translation function.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Awaitable, Callable

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.tools.http import ToolHttpClient

ToolHandler = Callable[[dict, CancelToken, ToolHttpClient], Awaitable[dict]]


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: dict  # JSON Schema for arguments
    handler: ToolHandler


class ToolRegistry:
    def __init__(self, http: ToolHttpClient):
        self.http = http
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def names(self) -> list[str]:
        return list(self._tools.keys())

    async def dispatch(self, name: str, args: dict, cancel: CancelToken) -> dict:
        if name not in self._tools:
            return {"error": f"unknown tool: {name}"}
        try:
            return await self._tools[name].handler(args, cancel, self.http)
        except Exception as e:
            return {"error": f"tool crashed: {type(e).__name__}: {e}"}

    # ----- Per-provider tool-definition emitters -----

    def for_anthropic(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.schema}
            for t in self._tools.values()
        ]

    def for_openai(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.schema,
                },
            }
            for t in self._tools.values()
        ]

    def for_gemini(self) -> list[dict]:
        # Gemini uses function_declarations; schema fields are similar to OpenAPI.
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.schema,
            }
            for t in self._tools.values()
        ]
