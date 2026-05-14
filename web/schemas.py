"""pydantic models for WebSocket JSON messages."""
from __future__ import annotations
from typing import Literal, Optional

from pydantic import BaseModel


class HelloMsg(BaseModel):
    type: Literal["hello"] = "hello"
    session_id: str = "new"
    provider: str = "anthropic"
    model: Optional[str] = None
    system: Optional[str] = None


class UserMsg(BaseModel):
    type: Literal["user"] = "user"
    content: str


class CancelMsg(BaseModel):
    type: Literal["cancel"] = "cancel"


class UpdateSettingsMsg(BaseModel):
    type: Literal["update_settings"] = "update_settings"
    provider: Optional[str] = None
    model: Optional[str] = None
    system: Optional[str] = None


class VoiceHelloMsg(BaseModel):
    type: Literal["hello"] = "hello"
    session_id: str = "new"
    voice: Literal["alloy", "verse", "shimmer"] = "alloy"


class StopMsg(BaseModel):
    type: Literal["stop"] = "stop"


class SessionStartedMsg(BaseModel):
    type: Literal["session_started"] = "session_started"
    session_id: str
    created: bool
    resumed_turns: Optional[int] = None
