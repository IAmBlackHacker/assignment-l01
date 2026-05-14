"""GET /api/sessions — list JSONL session files for the sidebar."""
from __future__ import annotations
import json
from pathlib import Path

from fastapi import APIRouter

from web.deps import HISTORY_DIR

router = APIRouter()


@router.get("/api/sessions")
async def list_sessions() -> list[dict]:
    if not HISTORY_DIR.exists():
        return []
    out = []
    for path in HISTORY_DIR.glob("*.jsonl"):
        try:
            lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        except OSError:
            continue
        title = path.stem
        for line in lines:
            try:
                t = json.loads(line)
            except ValueError:
                continue
            if t.get("role") == "user" and t.get("content"):
                title = t["content"][:60]
                break
        out.append({
            "id": path.stem,
            "title": title,
            "updated_at": path.stat().st_mtime,
            "message_count": len(lines),
        })
    out.sort(key=lambda s: s["updated_at"], reverse=True)
    return out
