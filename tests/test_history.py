import json
import tempfile
from pathlib import Path

import pytest

from elyos_chat.chat.history import History, Turn


def test_appends_and_snapshots():
    with tempfile.TemporaryDirectory() as d:
        h = History.new(Path(d))
        h.append(Turn(role="user", content="hi"))
        h.append(Turn(role="assistant", content="hello"))
        snap = h.snapshot()
        assert len(snap) == 2
        assert snap[0].role == "user"
        assert snap[1].content == "hello"


def test_persists_one_jsonl_line_per_turn():
    with tempfile.TemporaryDirectory() as d:
        h = History.new(Path(d))
        h.append(Turn(role="user", content="ping"))
        h.append(
            Turn(
                role="assistant",
                content="",
                tool_calls=[{"id": "t1", "name": "weather", "args": {"location": "London"}}],
            )
        )
        lines = h.path.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["role"] == "user"
        assert json.loads(lines[1])["tool_calls"][0]["name"] == "weather"


def test_resume_replays_from_disk():
    with tempfile.TemporaryDirectory() as d:
        h = History.new(Path(d))
        h.append(Turn(role="user", content="hi"))
        h.append(Turn(role="assistant", content="hello"))
        session_id = h.session_id

        h2 = History.resume(Path(d), session_id)
        snap = h2.snapshot()
        assert len(snap) == 2
        assert snap[0].content == "hi"
        assert snap[1].content == "hello"


def test_resume_last_picks_newest_session(tmp_path):
    import time
    h1 = History.new(tmp_path)
    h1.append(Turn(role="user", content="first"))
    time.sleep(0.01)
    h2 = History.new(tmp_path)
    h2.append(Turn(role="user", content="second"))

    h_last = History.resume_last(tmp_path)
    assert h_last is not None
    assert h_last.snapshot()[0].content == "second"


def test_resume_last_returns_none_when_no_sessions(tmp_path):
    assert History.resume_last(tmp_path) is None
