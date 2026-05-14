"""In-memory turn log with JSONL persistence and resume support."""
from __future__ import annotations
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class Turn:
    role: str  # "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)  # for assistant turns
    tool_results: list[dict] = field(default_factory=list)  # for tool turns
    cancelled: bool = False
    ts: float = field(default_factory=time.time)

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "Turn":
        return cls(
            role=d["role"],
            content=d.get("content", ""),
            tool_calls=d.get("tool_calls", []),
            tool_results=d.get("tool_results", []),
            cancelled=d.get("cancelled", False),
            ts=d.get("ts", time.time()),
        )


class History:
    def __init__(self, path: Path, turns: list[Turn], session_id: str):
        self.path = path
        self._turns = turns
        self.session_id = session_id

    @classmethod
    def new(cls, dir_: Path) -> "History":
        dir_.mkdir(parents=True, exist_ok=True)
        session_id = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
        path = dir_ / f"{session_id}.jsonl"
        path.touch()
        return cls(path=path, turns=[], session_id=session_id)

    @classmethod
    def resume(cls, dir_: Path, session_id: str) -> "History":
        path = dir_ / f"{session_id}.jsonl"
        turns = [Turn.from_dict(json.loads(line)) for line in path.read_text().splitlines() if line.strip()]
        return cls(path=path, turns=turns, session_id=session_id)

    @classmethod
    def resume_last(cls, dir_: Path) -> Optional["History"]:
        if not dir_.exists():
            return None
        files = sorted(dir_.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return None
        session_id = files[0].stem
        return cls.resume(dir_, session_id)

    def append(self, turn: Turn) -> None:
        self._turns.append(turn)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(turn.to_jsonl() + "\n")
            f.flush()

    def snapshot(self) -> list[Turn]:
        return list(self._turns)
