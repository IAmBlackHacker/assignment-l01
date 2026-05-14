"""Canonical events emitted by every Provider adapter.

The chat loop reads only these — it never touches an SDK type directly.
Adding a provider means translating SDK events into these shapes.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Union


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolUseStart:
    tool_use_id: str
    name: str


@dataclass(frozen=True)
class ToolUseArgsDelta:
    tool_use_id: str
    partial_json: str  # may be a fragment; chat loop accumulates


@dataclass(frozen=True)
class ToolUseEnd:
    tool_use_id: str
    name: str
    args: dict  # fully parsed arguments


@dataclass(frozen=True)
class TurnEnd:
    reason: Literal["stop", "tool_use", "cancelled", "max_tokens", "error"]


@dataclass(frozen=True)
class Error:
    message: str
    transient: bool = False


Event = Union[TextDelta, ToolUseStart, ToolUseArgsDelta, ToolUseEnd, TurnEnd, Error]
