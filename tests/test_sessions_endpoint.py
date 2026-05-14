import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.server import app
from web import deps


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(deps, "HISTORY_DIR", tmp_path)
    import web.sessions
    monkeypatch.setattr(web.sessions, "HISTORY_DIR", tmp_path)
    return TestClient(app), tmp_path


def _seed_session(dir_: Path, session_id: str, turns: list[dict]):
    path = dir_ / f"{session_id}.jsonl"
    with path.open("w") as f:
        for t in turns:
            f.write(json.dumps(t) + "\n")
    return path


def test_empty_dir_returns_empty_list(client):
    c, _ = client
    r = c.get("/api/sessions")
    assert r.status_code == 200
    assert r.json() == []


def test_lists_sessions_with_metadata(client):
    c, d = client
    _seed_session(d, "s1", [
        {"role": "user", "content": "hello", "ts": 100.0},
        {"role": "assistant", "content": "hi", "ts": 101.0},
    ])
    time.sleep(0.01)
    _seed_session(d, "s2", [{"role": "user", "content": "weather in tokyo", "ts": 200.0}])
    r = c.get("/api/sessions")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["id"] == "s2"
    assert body[1]["id"] == "s1"
    assert body[1]["title"] == "hello"
    assert body[0]["title"] == "weather in tokyo"
    assert body[1]["message_count"] == 2
    assert body[0]["message_count"] == 1


def test_skips_corrupt_files(client):
    c, d = client
    (d / "bad.jsonl").write_text("not json\n")
    _seed_session(d, "good", [{"role": "user", "content": "hi", "ts": 1.0}])
    r = c.get("/api/sessions")
    ids = [s["id"] for s in r.json()]
    assert "good" in ids
