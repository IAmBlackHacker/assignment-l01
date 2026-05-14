# Elyos CLI Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python command-line chat app with streaming LLM responses, tool calling against the Elyos weather + research APIs, graceful cancellation, persistent history, and three pluggable LLM providers (Claude, Gemini, OpenAI) selectable via `ELYOS_PROVIDER`.

**Architecture:** Layered async pipeline with a `Provider` Protocol that normalizes every SDK's streaming events into a canonical event stream (`TextDelta`, `ToolUseStart`, `ToolUseArgsDelta`, `ToolUseEnd`, `TurnEnd`, `Error`). The chat loop, renderer, and tool dispatcher are provider-agnostic. Cancellation is cooperative via an `asyncio.Event`-based `CancelToken`. History is in-memory + JSONL on disk for resume support.

**Tech Stack:** Python 3.11+, `asyncio`, `httpx`, `prompt_toolkit`, `rich`, `anthropic`, `openai`, `google-genai`, `python-dotenv`, `pytest`, `respx`.

**Reference spec:** [`docs/superpowers/specs/2026-05-14-elyos-chat-design.md`](../specs/2026-05-14-elyos-chat-design.md)

---

## File map

What gets created, in implementation order:

| File | Purpose | Tested? |
|---|---|---|
| `requirements.txt`, `.env.example`, `.gitignore`, `pyproject.toml` | Project setup | — |
| `src/elyos_chat/__init__.py`, `__main__.py` | Package entry | — |
| `src/elyos_chat/chat/events.py` | Canonical event dataclasses | — |
| `src/elyos_chat/chat/cancel.py` | `CancelToken` | smoke (in `test_cancel.py`) |
| `src/elyos_chat/chat/history.py` | In-memory + JSONL turn log | yes (TDD) |
| `src/elyos_chat/tools/http.py` | Shared `httpx` client + retry/backoff | yes (TDD) |
| `src/elyos_chat/tools/registry.py` | Canonical tool schemas + per-provider translation | — |
| `src/elyos_chat/tools/weather.py` | Weather tool handler | — |
| `src/elyos_chat/tools/research.py` | Research tool handler | — |
| `scripts/probe_api.py` | Systematic quirk probes | — |
| `docs/api-findings.md` | Quirk catalog | — |
| `src/elyos_chat/providers/base.py` | `Provider` Protocol + canonical message types | — |
| `src/elyos_chat/providers/anthropic.py` | Anthropic adapter | — |
| `src/elyos_chat/providers/openai.py` | OpenAI adapter | — |
| `src/elyos_chat/providers/gemini.py` | Gemini adapter | — |
| `src/elyos_chat/chat/session.py` | Turn orchestrator with tool loop | yes (TDD, FakeProvider) |
| `src/elyos_chat/cli/renderer.py` | Rich-based event renderer | — |
| `src/elyos_chat/cli/app.py` | Entrypoint, SIGINT handler, input loop | — |
| `src/elyos_chat/config.py` | Env-based provider/model selection | — |
| `tests/conftest.py` | `FakeProvider`, `respx` fixtures | — |
| `tests/test_*.py` | Four smoke test files | — |
| `README.md` | Setup, usage, design summary | — |

---

## Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `src/elyos_chat/__init__.py`
- Create: `src/elyos_chat/__main__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
anthropic>=0.40.0
openai>=1.50.0
google-genai>=0.3.0
httpx>=0.27.0
prompt_toolkit>=3.0.47
rich>=13.7.0
python-dotenv>=1.0.1
pytest>=8.0.0
pytest-asyncio>=0.23.0
respx>=0.21.1
```

- [ ] **Step 2: Create `.env.example`**

```
# Elyos tool API (provided by the assignment)
ELYOS_API_BASE=https://elyos-interview-907656039105.europe-west2.run.app
ELYOS_API_KEY=elyos2025

# Provider selection: anthropic | openai | gemini
ELYOS_PROVIDER=anthropic
ELYOS_MODEL=

# Provider keys — set the one matching ELYOS_PROVIDER
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
```

- [ ] **Step 3: Create `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.env
.pytest_cache/
.elyos_chat/
.DS_Store
*.egg-info/
dist/
build/
```

- [ ] **Step 4: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "elyos-chat"
version = "0.1.0"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 5: Create `src/elyos_chat/__init__.py`**

```python
"""Elyos CLI chat — streaming LLM with tool use, cancellation, and history."""
__version__ = "0.1.0"
```

- [ ] **Step 6: Create `src/elyos_chat/__main__.py`**

```python
from elyos_chat.cli.app import main

if __name__ == "__main__":
    main()
```

(`main` will be defined in Task 14; this file just wires it up so `python -m elyos_chat` works once everything is in place.)

- [ ] **Step 7: Set up the venv and install**

```bash
cd /Users/lokesh/Desktop/TEMP/elyos-assignment
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

Expected: clean install, no errors. `pip list` shows all packages from `requirements.txt`.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .env.example .gitignore pyproject.toml src/elyos_chat/__init__.py src/elyos_chat/__main__.py
git commit -m "Scaffold project: deps, package layout, entry point"
```

---

## Task 2: Canonical events

**Files:**
- Create: `src/elyos_chat/chat/__init__.py`
- Create: `src/elyos_chat/chat/events.py`

No tests — these are dataclasses with no behavior.

- [ ] **Step 1: Create `src/elyos_chat/chat/__init__.py`** (empty file)

- [ ] **Step 2: Create `src/elyos_chat/chat/events.py`**

```python
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
```

- [ ] **Step 3: Commit**

```bash
git add src/elyos_chat/chat/
git commit -m "Add canonical Event types for provider-agnostic streaming"
```

---

## Task 3: CancelToken (TDD)

**Files:**
- Create: `src/elyos_chat/chat/cancel.py`
- Create: `tests/__init__.py`
- Create: `tests/test_cancel_token.py`

- [ ] **Step 1: Write the failing test**

Create `tests/__init__.py` (empty) and `tests/test_cancel_token.py`:

```python
import asyncio
import pytest

from elyos_chat.chat.cancel import CancelToken


async def test_token_starts_uncancelled():
    token = CancelToken()
    assert token.cancelled() is False


async def test_cancel_sets_flag():
    token = CancelToken()
    token.cancel()
    assert token.cancelled() is True


async def test_wait_unblocks_when_cancelled():
    token = CancelToken()

    async def cancel_soon():
        await asyncio.sleep(0.01)
        token.cancel()

    await asyncio.gather(cancel_soon(), token.wait())
    assert token.cancelled() is True


async def test_cancel_is_idempotent():
    token = CancelToken()
    token.cancel()
    token.cancel()
    assert token.cancelled() is True
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
pytest tests/test_cancel_token.py -v
```

Expected: import error — `elyos_chat.chat.cancel` does not exist.

- [ ] **Step 3: Implement `CancelToken`**

Create `src/elyos_chat/chat/cancel.py`:

```python
"""Cooperative cancellation primitive used across a single turn."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field


@dataclass
class CancelToken:
    event: asyncio.Event = field(default_factory=asyncio.Event)

    def cancel(self) -> None:
        self.event.set()

    def cancelled(self) -> bool:
        return self.event.is_set()

    async def wait(self) -> None:
        await self.event.wait()
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
pytest tests/test_cancel_token.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/elyos_chat/chat/cancel.py tests/__init__.py tests/test_cancel_token.py
git commit -m "Add CancelToken with cooperative cancel/wait semantics"
```

---

## Task 4: History store (TDD)

**Files:**
- Create: `src/elyos_chat/chat/history.py`
- Create: `tests/test_history.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_history.py`:

```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_history.py -v
```

Expected: import error.

- [ ] **Step 3: Implement `History`**

Create `src/elyos_chat/chat/history.py`:

```python
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
```

- [ ] **Step 4: Run to confirm passing**

```bash
pytest tests/test_history.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/elyos_chat/chat/history.py tests/test_history.py
git commit -m "Add History with append-only turns and JSONL persistence"
```

---

## Task 5: HTTP client with retry/backoff (TDD)

**Files:**
- Create: `src/elyos_chat/tools/__init__.py`
- Create: `src/elyos_chat/tools/http.py`
- Create: `tests/test_http_retry.py`

- [ ] **Step 1: Create `src/elyos_chat/tools/__init__.py`** (empty)

- [ ] **Step 2: Write the failing test**

Create `tests/test_http_retry.py`:

```python
import httpx
import pytest
import respx

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.tools.http import ToolHttpClient


BASE = "https://example.test"


@pytest.fixture
async def client():
    c = ToolHttpClient(base_url=BASE, api_key="k", max_attempts=3, base_backoff=0.001)
    yield c
    await c.aclose()


@respx.mock
async def test_happy_path_returns_ok(client):
    respx.get(f"{BASE}/weather", params={"location": "London"}).mock(
        return_value=httpx.Response(200, json={"temp_c": 12})
    )
    result = await client.get("/weather", {"location": "London"}, CancelToken())
    assert result.is_ok
    assert result.value == {"temp_c": 12}


@respx.mock
async def test_retries_503_then_succeeds(client):
    route = respx.get(f"{BASE}/research").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"summary": "ok"}),
        ]
    )
    result = await client.get("/research", {"topic": "solar"}, CancelToken())
    assert result.is_ok
    assert route.call_count == 2


@respx.mock
async def test_gives_up_after_max_attempts(client):
    respx.get(f"{BASE}/research").mock(return_value=httpx.Response(503))
    result = await client.get("/research", {"topic": "x"}, CancelToken())
    assert result.is_err
    assert result.is_transient is True


@respx.mock
async def test_4xx_is_not_retried(client):
    route = respx.get(f"{BASE}/weather").mock(return_value=httpx.Response(400, json={"error": "bad"}))
    result = await client.get("/weather", {"location": ""}, CancelToken())
    assert result.is_err
    assert route.call_count == 1
    assert result.is_transient is False


@respx.mock
async def test_non_json_body_surfaces_as_error(client):
    respx.get(f"{BASE}/weather").mock(
        return_value=httpx.Response(200, content=b"<html>oops</html>", headers={"content-type": "text/html"})
    )
    result = await client.get("/weather", {"location": "x"}, CancelToken())
    assert result.is_err
    assert "non-json" in result.error.lower()


@respx.mock
async def test_cancel_aborts_between_retries(client):
    respx.get(f"{BASE}/research").mock(return_value=httpx.Response(503))
    token = CancelToken()
    token.cancel()  # already cancelled before any call
    result = await client.get("/research", {"topic": "x"}, token)
    assert result.is_err
    assert "cancel" in result.error.lower()


@respx.mock
async def test_sends_x_api_key_header(client):
    route = respx.get(f"{BASE}/weather").mock(return_value=httpx.Response(200, json={}))
    await client.get("/weather", {"location": "x"}, CancelToken())
    assert route.calls[0].request.headers["X-API-Key"] == "k"
```

- [ ] **Step 3: Run to confirm failure**

```bash
pytest tests/test_http_retry.py -v
```

Expected: import error.

- [ ] **Step 4: Implement `ToolHttpClient`**

Create `src/elyos_chat/tools/http.py`:

```python
"""Single shared HTTP client for all tool endpoints.

Retry policy: 3 attempts max, exponential backoff with jitter, honor Retry-After.
Returns Result objects — never raises out to callers. All errors surface as
data the LLM can read and reason about.
"""
from __future__ import annotations
import asyncio
import random
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

import httpx

from elyos_chat.chat.cancel import CancelToken

T = TypeVar("T")

TRANSIENT_STATUSES = {429, 502, 503, 504}


@dataclass
class Result(Generic[T]):
    value: Optional[T] = None
    error: Optional[str] = None
    is_transient: bool = False

    @property
    def is_ok(self) -> bool:
        return self.error is None

    @property
    def is_err(self) -> bool:
        return self.error is not None

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        return cls(value=value)

    @classmethod
    def err(cls, msg: str, transient: bool = False) -> "Result[T]":
        return cls(error=msg, is_transient=transient)


class ToolHttpClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        max_attempts: int = 3,
        base_backoff: float = 0.25,
        connect_timeout: float = 5.0,
        read_timeout: float = 15.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_attempts = max_attempts
        self.base_backoff = base_backoff
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=connect_timeout, read=read_timeout, write=5.0, pool=5.0),
            headers={"X-API-Key": api_key},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: dict, cancel: CancelToken) -> Result[dict]:
        url = f"{self.base_url}{path}"
        last_err = "unknown"
        for attempt in range(self.max_attempts):
            if cancel.cancelled():
                return Result.err("cancelled", transient=False)
            try:
                resp = await self._client.get(url, params=params)
            except httpx.ReadTimeout:
                last_err = "read-timeout"
                if not await self._sleep_or_cancel(attempt, None, cancel):
                    return Result.err("cancelled", transient=False)
                continue
            except httpx.ConnectError as e:
                last_err = f"connect-error: {e}"
                if not await self._sleep_or_cancel(attempt, None, cancel):
                    return Result.err("cancelled", transient=False)
                continue
            except httpx.HTTPError as e:
                return Result.err(f"http-error: {e}", transient=False)

            if resp.status_code in TRANSIENT_STATUSES:
                last_err = f"transient-status:{resp.status_code}"
                retry_after = resp.headers.get("Retry-After")
                if not await self._sleep_or_cancel(attempt, retry_after, cancel):
                    return Result.err("cancelled", transient=False)
                continue

            if resp.status_code >= 400:
                return Result.err(f"http-{resp.status_code}: {resp.text[:200]}", transient=False)

            ctype = resp.headers.get("content-type", "")
            if "json" not in ctype:
                return Result.err(f"non-json:{resp.text[:200]}", transient=False)
            try:
                return Result.ok(resp.json())
            except ValueError as e:
                return Result.err(f"invalid-json:{e}", transient=False)

        return Result.err(f"exhausted retries: {last_err}", transient=True)

    async def _sleep_or_cancel(self, attempt: int, retry_after: Optional[str], cancel: CancelToken) -> bool:
        """Sleep between retries. Returns False if cancelled during sleep."""
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = self.base_backoff * (2 ** attempt)
        else:
            delay = self.base_backoff * (2 ** attempt) + random.uniform(0, self.base_backoff)
        try:
            await asyncio.wait_for(cancel.wait(), timeout=delay)
            return False  # cancel fired during sleep
        except asyncio.TimeoutError:
            return True   # slept fully
```

- [ ] **Step 5: Run to confirm passing**

```bash
pytest tests/test_http_retry.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add src/elyos_chat/tools/__init__.py src/elyos_chat/tools/http.py tests/test_http_retry.py
git commit -m "Add ToolHttpClient with retry, backoff, cancel and content-type guards"
```

---

## Task 6: Tool registry with per-provider schema translation

**Files:**
- Create: `src/elyos_chat/tools/registry.py`

No tests (covered indirectly by `test_session_tool_loop.py` in Task 12).

- [ ] **Step 1: Create `src/elyos_chat/tools/registry.py`**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add src/elyos_chat/tools/registry.py
git commit -m "Add ToolRegistry with canonical schema and per-provider translation"
```

---

## Task 7: Weather and research tool handlers

**Files:**
- Create: `src/elyos_chat/tools/weather.py`
- Create: `src/elyos_chat/tools/research.py`

Quirk-specific normalization will be added after the probe script runs (Task 8) and findings are captured (Task 9). For now, handlers do arg validation and call the HTTP layer.

- [ ] **Step 1: Create `src/elyos_chat/tools/weather.py`**

```python
"""Weather tool handler.

Quirk handlers should be added here referencing finding IDs from
docs/api-findings.md once the probe script has run.
"""
from __future__ import annotations
from elyos_chat.chat.cancel import CancelToken
from elyos_chat.tools.http import ToolHttpClient
from elyos_chat.tools.registry import ToolSpec


WEATHER_SCHEMA = {
    "type": "object",
    "properties": {
        "location": {
            "type": "string",
            "description": "City name or location identifier (e.g. 'London', 'Tokyo').",
        }
    },
    "required": ["location"],
}


async def weather_handler(args: dict, cancel: CancelToken, http: ToolHttpClient) -> dict:
    location = (args.get("location") or "").strip()
    if not location:
        return {
            "error": "missing location",
            "guidance": "Ask the user which location they want the weather for.",
        }
    result = await http.get("/weather", {"location": location}, cancel)
    if result.is_err:
        return {"error": result.error, "transient": result.is_transient}
    return _normalise(result.value)


def _normalise(body: dict) -> dict:
    # Placeholder. Add quirk handlers here referencing finding IDs (e.g. F-01).
    return body


WEATHER_TOOL = ToolSpec(
    name="weather",
    description="Get current weather for a location. Fast (~200ms).",
    schema=WEATHER_SCHEMA,
    handler=weather_handler,
)
```

- [ ] **Step 2: Create `src/elyos_chat/tools/research.py`**

```python
"""Research tool handler.

Quirk handlers should be added here referencing finding IDs from
docs/api-findings.md once the probe script has run.
"""
from __future__ import annotations
from elyos_chat.chat.cancel import CancelToken
from elyos_chat.tools.http import ToolHttpClient
from elyos_chat.tools.registry import ToolSpec


RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {
            "type": "string",
            "description": "Topic to research (e.g. 'solar energy', 'CRISPR gene editing').",
        }
    },
    "required": ["topic"],
}


async def research_handler(args: dict, cancel: CancelToken, http: ToolHttpClient) -> dict:
    topic = (args.get("topic") or "").strip()
    if not topic:
        return {
            "error": "missing topic",
            "guidance": "Ask the user what topic to research.",
        }
    result = await http.get("/research", {"topic": topic}, cancel)
    if result.is_err:
        return {"error": result.error, "transient": result.is_transient}
    return _normalise(result.value)


def _normalise(body: dict) -> dict:
    # Placeholder. Add quirk handlers here referencing finding IDs (e.g. F-03).
    return body


RESEARCH_TOOL = ToolSpec(
    name="research",
    description="Research a topic in depth. Slow (3-8s).",
    schema=RESEARCH_SCHEMA,
    handler=research_handler,
)
```

- [ ] **Step 3: Commit**

```bash
git add src/elyos_chat/tools/weather.py src/elyos_chat/tools/research.py
git commit -m "Add weather and research tool handlers (pre-quirk-discovery)"
```

---

## Task 8: API probe script

**Files:**
- Create: `scripts/probe_api.py`

This is the workhorse of the assignment's API-discovery section. It runs systematic experiments and prints structured output that informs `docs/api-findings.md`.

- [ ] **Step 1: Create `scripts/probe_api.py`**

```python
"""Systematic Elyos API probe.

Run: python scripts/probe_api.py
Reads ELYOS_API_BASE and ELYOS_API_KEY from env.

Prints findings as Markdown so the output can be piped or copied into
docs/api-findings.md. Each probe block is labeled with a category so
the operator can pick which to deepen.
"""
from __future__ import annotations
import asyncio
import os
import statistics
import time
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = os.environ["ELYOS_API_BASE"]
KEY = os.environ["ELYOS_API_KEY"]
H = {"X-API-Key": KEY}


def section(title: str) -> None:
    print(f"\n## {title}\n")


async def show(client, label, method, path, params=None, headers=None):
    headers = headers if headers is not None else H
    t0 = time.perf_counter()
    try:
        resp = await client.get(f"{BASE}{path}", params=params, headers=headers)
        dt = (time.perf_counter() - t0) * 1000
        body = resp.text
        ctype = resp.headers.get("content-type", "")
        print(f"- **{label}** → {resp.status_code} `{ctype}` {dt:.0f}ms")
        print(f"  ```\n  {body[:300]}\n  ```")
    except Exception as e:
        print(f"- **{label}** → EXC {type(e).__name__}: {e}")


async def auth_probes(client):
    section("Auth")
    await show(client, "no key", "GET", "/weather", {"location": "London"}, headers={})
    await show(client, "wrong key", "GET", "/weather", {"location": "London"}, headers={"X-API-Key": "wrong"})
    await show(client, "lowercase header", "GET", "/weather", {"location": "London"}, headers={"x-api-key": KEY})


async def param_probes(client):
    section("Weather params")
    await show(client, "happy", "GET", "/weather", {"location": "London"})
    await show(client, "missing", "GET", "/weather", {})
    await show(client, "empty", "GET", "/weather", {"location": ""})
    await show(client, "unicode", "GET", "/weather", {"location": "São Paulo"})
    await show(client, "very long", "GET", "/weather", {"location": "A" * 500})
    await show(client, "whitespace", "GET", "/weather", {"location": "  London  "})
    await show(client, "unknown extra", "GET", "/weather", {"location": "London", "format": "json"})

    section("Research params")
    await show(client, "happy", "GET", "/research", {"topic": "solar energy"})
    await show(client, "missing", "GET", "/research", {})
    await show(client, "empty", "GET", "/research", {"topic": ""})
    await show(client, "encoded space", "GET", "/research", {"topic": "solar+energy"})
    await show(client, "unicode", "GET", "/research", {"topic": "café science"})


async def determinism_probes(client):
    section("Determinism — weather")
    for i in range(3):
        await show(client, f"London #{i+1}", "GET", "/weather", {"location": "London"})

    section("Determinism — research")
    for i in range(3):
        await show(client, f"solar #{i+1}", "GET", "/research", {"topic": "solar energy"})


async def timing_probe(client, path, params, n):
    section(f"Timing — {path} ({n} calls)")
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            r = await client.get(f"{BASE}{path}", params=params, headers=H)
            times.append((time.perf_counter() - t0) * 1000)
        except Exception as e:
            print(f"- EXC {e}")
    if times:
        print(f"- n={len(times)}, p50={statistics.median(times):.0f}ms, "
              f"min={min(times):.0f}ms, max={max(times):.0f}ms")


async def concurrency_probe(client):
    section("Concurrency — 5 parallel /research")
    t0 = time.perf_counter()
    tasks = [
        client.get(f"{BASE}/research", params={"topic": f"topic-{i}"}, headers=H)
        for i in range(5)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    dt = (time.perf_counter() - t0) * 1000
    print(f"- total wall: {dt:.0f}ms")
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"  - task {i}: EXC {type(r).__name__}")
        else:
            print(f"  - task {i}: {r.status_code} {len(r.text)} bytes")


async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        await auth_probes(client)
        await param_probes(client)
        await determinism_probes(client)
        await timing_probe(client, "/weather", {"location": "London"}, 5)
        await timing_probe(client, "/research", {"topic": "solar"}, 3)
        await concurrency_probe(client)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run the probe and capture findings**

```bash
source .venv/bin/activate
python scripts/probe_api.py | tee probe-output.md
```

Expected: a structured Markdown dump. Read each section. Note anything surprising — non-200 with body, schema differences across calls, slow calls, timeouts, header case sensitivity, etc.

- [ ] **Step 3: Commit the script (not the output)**

```bash
git add scripts/probe_api.py
git commit -m "Add API probe script for systematic quirk discovery"
```

(The output goes into `docs/api-findings.md` in Task 9.)

---

## Task 9: Capture findings and update tool handlers

**Files:**
- Create: `docs/api-findings.md`
- Modify: `src/elyos_chat/tools/weather.py` — add quirk handlers
- Modify: `src/elyos_chat/tools/research.py` — add quirk handlers

This task is partly mechanical (write findings) and partly judgment (decide handler shape). The skeleton is fixed; the contents depend on what the probe surfaced.

- [ ] **Step 1: Create `docs/api-findings.md` with the template and observed findings**

Template structure (replace `<...>` with real observations from Task 8's run):

```markdown
# Elyos API findings

Base URL: `https://elyos-interview-907656039105.europe-west2.run.app`
Probe script: `scripts/probe_api.py`
Probed on: <YYYY-MM-DD>

## Summary

| ID | Endpoint | Quirk | Severity | Handler |
|---|---|---|---|---|
| F-01 | <endpoint> | <one-line summary> | low/med/high | <file:function> |

---

### F-01: <title>

- **Repro:**
  ```bash
  curl -H "X-API-Key: $ELYOS_API_KEY" "<url>"
  ```
- **Observed:** <what came back>
- **Expected:** <what one would expect>
- **Impact:** <what could go wrong if unhandled>
- **Handler:** <`tools/<file>.py` — `<function>`>

### F-02: <title>
...
```

Fill in one section per quirk found in the probe output. Aim for 4–8 findings; this is the highest-value section of the Loom video. Prioritize quirks where the model could be tricked or the user could be confused.

- [ ] **Step 2: Update `src/elyos_chat/tools/weather.py` `_normalise` to handle observed weather quirks**

For each weather-related finding (e.g. F-XX: response sometimes returns null for `humidity`), update the `_normalise` function to handle it. Each branch should have a one-line comment with the finding ID.

Example (illustrative — actual code depends on findings):

```python
def _normalise(body: dict) -> dict:
    # F-02: humidity may be null — coerce to "unknown" so the model doesn't render "null"
    if body.get("humidity") is None:
        body = {**body, "humidity": "unknown"}
    # F-04: temperature sometimes returned as string "12C" — strip suffix
    temp = body.get("temperature")
    if isinstance(temp, str) and temp.endswith("C"):
        body = {**body, "temperature": float(temp[:-1])}
    return body
```

- [ ] **Step 3: Update `src/elyos_chat/tools/research.py` `_normalise` similarly**

Same shape — one branch per finding, finding ID in a comment.

- [ ] **Step 4: Commit**

```bash
git add docs/api-findings.md src/elyos_chat/tools/weather.py src/elyos_chat/tools/research.py
git commit -m "Document API quirks and add normalization handlers"
```

---

## Task 10: Provider Protocol + canonical messages

**Files:**
- Create: `src/elyos_chat/providers/__init__.py` (empty)
- Create: `src/elyos_chat/providers/base.py`

- [ ] **Step 1: Create `src/elyos_chat/providers/__init__.py`** (empty)

- [ ] **Step 2: Create `src/elyos_chat/providers/base.py`**

```python
"""Provider Protocol — the only seam between the chat loop and SDKs.

Every adapter:
  1. Translates canonical Turn list to SDK message shape.
  2. Translates SDK tool-schema list (registry.for_<name>()).
  3. Streams SDK events into canonical Event objects.
  4. Cooperates with CancelToken — closes the stream cleanly on cancel.
"""
from __future__ import annotations
from typing import AsyncIterator, Protocol

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.chat.events import Event
from elyos_chat.chat.history import Turn


class Provider(Protocol):
    name: str
    model: str

    async def stream_turn(
        self,
        turns: list[Turn],
        tools: list[dict],            # provider-specific tool definitions
        cancel: CancelToken,
        system: str | None = None,
    ) -> AsyncIterator[Event]:
        ...
```

- [ ] **Step 3: Commit**

```bash
git add src/elyos_chat/providers/
git commit -m "Add Provider Protocol — canonical seam between chat loop and SDKs"
```

---

## Task 11: Anthropic adapter

**Files:**
- Create: `src/elyos_chat/providers/anthropic.py`

- [ ] **Step 1: Create `src/elyos_chat/providers/anthropic.py`**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add src/elyos_chat/providers/anthropic.py
git commit -m "Add Anthropic provider with streaming + tool-use event normalization"
```

---

## Task 12: OpenAI adapter

**Files:**
- Create: `src/elyos_chat/providers/openai.py`

- [ ] **Step 1: Create `src/elyos_chat/providers/openai.py`**

```python
"""OpenAI adapter — chat.completions streaming with tool calls."""
from __future__ import annotations
import asyncio
import json
import os
from typing import AsyncIterator

from openai import AsyncOpenAI

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.chat.events import (
    Error, Event, TextDelta, ToolUseArgsDelta, ToolUseEnd, ToolUseStart, TurnEnd,
)
from elyos_chat.chat.history import Turn

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str | None = None):
        self.model = model or DEFAULT_MODEL
        self._client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    async def stream_turn(self, turns, tools, cancel, system=None) -> AsyncIterator[Event]:
        messages = self._to_messages(turns, system)
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                stream=True,
            )
            pending: dict[int, dict] = {}  # tool_call index → {"id", "name", "args": []}
            announced: set[int] = set()
            stop_reason = "stop"
            async for chunk in stream:
                if cancel.cancelled():
                    yield TurnEnd(reason="cancelled")
                    await stream.close()
                    return
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta.content:
                    yield TextDelta(text=delta.content)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        slot = pending.setdefault(idx, {"id": None, "name": None, "args": []})
                        if tc.id:
                            slot["id"] = tc.id
                        if tc.function and tc.function.name:
                            slot["name"] = tc.function.name
                        if idx not in announced and slot["id"] and slot["name"]:
                            announced.add(idx)
                            yield ToolUseStart(tool_use_id=slot["id"], name=slot["name"])
                        if tc.function and tc.function.arguments:
                            slot["args"].append(tc.function.arguments)
                            if slot["id"]:
                                yield ToolUseArgsDelta(
                                    tool_use_id=slot["id"],
                                    partial_json=tc.function.arguments,
                                )
                if choice.finish_reason:
                    stop_reason = choice.finish_reason
            # Emit ToolUseEnd for each pending tool, then TurnEnd.
            for slot in pending.values():
                args_text = "".join(slot["args"])
                try:
                    args = json.loads(args_text) if args_text else {}
                except json.JSONDecodeError:
                    args = {"_raw": args_text}
                yield ToolUseEnd(tool_use_id=slot["id"], name=slot["name"], args=args)
            reason = "tool_use" if stop_reason == "tool_calls" else "stop"
            yield TurnEnd(reason=reason)
        except asyncio.CancelledError:
            yield TurnEnd(reason="cancelled")
        except Exception as e:
            yield Error(message=f"openai: {type(e).__name__}: {e}", transient=True)
            yield TurnEnd(reason="error")

    def _to_messages(self, turns: list[Turn], system: str | None) -> list[dict]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        for t in turns:
            if t.role == "user":
                msgs.append({"role": "user", "content": t.content})
            elif t.role == "assistant":
                m = {"role": "assistant", "content": t.content or None}
                if t.tool_calls:
                    m["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"]),
                            },
                        }
                        for tc in t.tool_calls
                    ]
                msgs.append(m)
            elif t.role == "tool":
                for r in t.tool_results:
                    msgs.append({
                        "role": "tool",
                        "tool_call_id": r["id"],
                        "content": json.dumps(r["content"]),
                    })
        return msgs
```

- [ ] **Step 2: Commit**

```bash
git add src/elyos_chat/providers/openai.py
git commit -m "Add OpenAI provider with streaming + tool-call event normalization"
```

---

## Task 13: Gemini adapter

**Files:**
- Create: `src/elyos_chat/providers/gemini.py`

- [ ] **Step 1: Create `src/elyos_chat/providers/gemini.py`**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add src/elyos_chat/providers/gemini.py
git commit -m "Add Gemini provider with streaming + function-call event normalization"
```

---

## Task 14: Chat session orchestrator (TDD with FakeProvider)

**Files:**
- Create: `tests/conftest.py`
- Create: `src/elyos_chat/chat/session.py`
- Create: `tests/test_session_tool_loop.py`

- [ ] **Step 1: Create `tests/conftest.py` with `FakeProvider`**

```python
"""Shared test fixtures."""
from __future__ import annotations
from typing import AsyncIterator

import pytest

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.chat.events import Event


class FakeProvider:
    """Scripted provider: yields a pre-built list of events on each call.

    Supports multi-turn: each entry in `scripts` is one list of events that
    the next stream_turn() call returns.
    """
    name = "fake"
    model = "fake-1"

    def __init__(self, scripts: list[list[Event]]):
        self.scripts = scripts
        self.calls: list[dict] = []

    async def stream_turn(
        self, turns, tools, cancel: CancelToken, system=None,
    ) -> AsyncIterator[Event]:
        self.calls.append({"turns": list(turns), "tools": tools})
        if not self.scripts:
            return
        events = self.scripts.pop(0)
        for ev in events:
            if cancel.cancelled():
                return
            yield ev
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_session_tool_loop.py`:

```python
import asyncio
import tempfile
from pathlib import Path

import pytest

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.chat.events import (
    Error, TextDelta, ToolUseEnd, ToolUseStart, TurnEnd,
)
from elyos_chat.chat.history import History
from elyos_chat.chat.session import ChatSession
from elyos_chat.tools.registry import ToolRegistry, ToolSpec


class StubHttp:
    async def aclose(self): pass


class CapturingRenderer:
    def __init__(self):
        self.events = []
    def write(self, text): self.events.append(("text", text))
    def begin_tool(self, name): self.events.append(("tool_start", name))
    def end_tool(self, name, result): self.events.append(("tool_end", name, result))
    def show_error(self, msg): self.events.append(("error", msg))
    def turn_done(self): self.events.append(("turn_done",))


async def fake_weather(args, cancel, http):
    return {"temp_c": 12, "echo": args}


def build_registry():
    r = ToolRegistry(http=StubHttp())
    r.register(ToolSpec(name="weather", description="", schema={}, handler=fake_weather))
    return r


async def test_simple_text_response_no_tool(tmp_path):
    from tests.conftest import FakeProvider
    provider = FakeProvider(scripts=[[TextDelta("hello"), TurnEnd(reason="stop")]])
    history = History.new(tmp_path)
    renderer = CapturingRenderer()
    session = ChatSession(provider=provider, registry=build_registry(),
                         history=history, renderer=renderer)
    await session.handle_user_input("hi")

    snap = history.snapshot()
    assert snap[0].role == "user"
    assert snap[1].role == "assistant"
    assert snap[1].content == "hello"
    assert ("text", "hello") in renderer.events


async def test_tool_call_loop_runs_handler_and_replies(tmp_path):
    from tests.conftest import FakeProvider
    provider = FakeProvider(scripts=[
        [
            ToolUseStart(tool_use_id="t1", name="weather"),
            ToolUseEnd(tool_use_id="t1", name="weather", args={"location": "London"}),
            TurnEnd(reason="tool_use"),
        ],
        [
            TextDelta("It's 12°C in London."),
            TurnEnd(reason="stop"),
        ],
    ])
    history = History.new(tmp_path)
    renderer = CapturingRenderer()
    session = ChatSession(provider=provider, registry=build_registry(),
                         history=history, renderer=renderer)
    await session.handle_user_input("weather in London?")

    roles = [t.role for t in history.snapshot()]
    assert roles == ["user", "assistant", "tool", "assistant"]
    tool_turn = history.snapshot()[2]
    assert tool_turn.tool_results[0]["content"]["temp_c"] == 12
    final_assistant = history.snapshot()[3]
    assert "12" in final_assistant.content


async def test_cancel_truncates_assistant_turn(tmp_path):
    from tests.conftest import FakeProvider
    provider = FakeProvider(scripts=[[
        TextDelta("partial"),
        TextDelta(" answer"),
        TurnEnd(reason="stop"),
    ]])
    history = History.new(tmp_path)
    renderer = CapturingRenderer()
    session = ChatSession(provider=provider, registry=build_registry(),
                         history=history, renderer=renderer)

    async def cancel_quickly():
        await asyncio.sleep(0)
        session.cancel_current()

    await asyncio.gather(session.handle_user_input("go"), cancel_quickly())

    # Either truncated assistant or no assistant turn at all is acceptable;
    # we assert no crash and history is coherent.
    snap = history.snapshot()
    assert snap[0].role == "user"


async def test_max_tool_iterations_breaks_loop(tmp_path):
    from tests.conftest import FakeProvider
    # Build 10 scripts each ending in a tool_use — should hit cap at 8.
    scripts = []
    for i in range(10):
        scripts.append([
            ToolUseStart(tool_use_id=f"t{i}", name="weather"),
            ToolUseEnd(tool_use_id=f"t{i}", name="weather", args={"location": "X"}),
            TurnEnd(reason="tool_use"),
        ])
    provider = FakeProvider(scripts=scripts)
    history = History.new(tmp_path)
    renderer = CapturingRenderer()
    session = ChatSession(provider=provider, registry=build_registry(),
                         history=history, renderer=renderer,
                         max_tool_iterations=8)
    await session.handle_user_input("loop forever")

    # Provider should have been called 8 times max.
    assert len(provider.calls) <= 8
    # An error/guard turn should appear at the tail.
    assert any("max tool iterations" in (t.content or "") or
               any("max" in str(r) for r in t.tool_results)
               for t in history.snapshot())
```

- [ ] **Step 3: Run to confirm failure**

```bash
pytest tests/test_session_tool_loop.py -v
```

Expected: import error.

- [ ] **Step 4: Implement `ChatSession`**

Create `src/elyos_chat/chat/session.py`:

```python
"""ChatSession — orchestrates a turn from user input to final assistant reply.

Owns the per-turn CancelToken; loops over the provider until either a stop
reason or MAX_TOOL_ITERATIONS is reached. Tool calls run in parallel.
"""
from __future__ import annotations
import asyncio
import uuid
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

            if cancelled or not pending_tools:
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

        # Max iterations hit.
        self.renderer.show_error(f"max tool iterations reached ({self.max_tool_iterations})")
        self.history.append(Turn(
            role="tool",
            tool_results=[{"id": "guard", "name": "session", "content": {"error": f"max tool iterations reached"}, "is_error": True}],
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
```

- [ ] **Step 5: Run to confirm passing**

```bash
pytest tests/test_session_tool_loop.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/elyos_chat/chat/session.py tests/conftest.py tests/test_session_tool_loop.py
git commit -m "Add ChatSession orchestrator with parallel tool dispatch + MAX_TOOL guard"
```

---

## Task 15: Cancellation through the chat session (verification test)

**Files:**
- Create: `tests/test_cancel.py`

A targeted smoke test that simulates a long-running provider stream and asserts that calling `session.cancel_current()` mid-stream lands cleanly.

- [ ] **Step 1: Write the test**

```python
import asyncio
import pytest

from elyos_chat.chat.events import TextDelta, TurnEnd
from elyos_chat.chat.history import History
from elyos_chat.chat.session import ChatSession
from elyos_chat.tools.registry import ToolRegistry


class SlowProvider:
    name = "slow"
    model = "slow-1"
    def __init__(self, n=100):
        self.n = n

    async def stream_turn(self, turns, tools, cancel, system=None):
        for i in range(self.n):
            if cancel.cancelled():
                yield TurnEnd(reason="cancelled")
                return
            await asyncio.sleep(0.005)
            yield TextDelta(text=f"chunk{i}")
        yield TurnEnd(reason="stop")


class NoOpRenderer:
    def __init__(self): self.text = ""
    def write(self, t): self.text += t
    def begin_tool(self, n): pass
    def end_tool(self, n, r): pass
    def show_error(self, m): pass
    def turn_done(self): pass


class StubHttp:
    async def aclose(self): pass


async def test_cancel_mid_stream_unwinds_cleanly(tmp_path):
    session = ChatSession(
        provider=SlowProvider(n=100),
        registry=ToolRegistry(http=StubHttp()),
        history=History.new(tmp_path),
        renderer=NoOpRenderer(),
    )

    async def cancel_after_a_bit():
        await asyncio.sleep(0.03)
        session.cancel_current()

    await asyncio.gather(session.handle_user_input("go"), cancel_after_a_bit())

    snap = session.history.snapshot()
    assert snap[0].role == "user"
    assert snap[1].role == "assistant"
    assert snap[1].cancelled is True
    # Should have stopped well before completing all 100 chunks.
    assert len(snap[1].content) < len("chunk") * 100
```

- [ ] **Step 2: Run**

```bash
pytest tests/test_cancel.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cancel.py
git commit -m "Verify mid-stream cancellation flows through ChatSession cleanly"
```

---

## Task 16: Renderer

**Files:**
- Create: `src/elyos_chat/cli/__init__.py` (empty)
- Create: `src/elyos_chat/cli/renderer.py`

- [ ] **Step 1: Create `src/elyos_chat/cli/__init__.py`** (empty)

- [ ] **Step 2: Create `src/elyos_chat/cli/renderer.py`**

```python
"""Rich-based renderer for the canonical event stream."""
from __future__ import annotations
import json
from rich.console import Console
from rich.spinner import Spinner
from rich.live import Live


class Renderer:
    """Streams assistant text inline; shows a spinner during tool calls.

    Designed to be simple — no Live region juggling. Spinner appears as a
    line below the streamed text and is replaced by the tool result.
    """
    def __init__(self, console: Console | None = None):
        self.console = console or Console()
        self._spinner_live: Live | None = None
        self._has_written_text = False

    def write(self, text: str) -> None:
        if not self._has_written_text:
            self.console.print("[bold cyan]assistant:[/] ", end="")
            self._has_written_text = True
        self.console.print(text, end="", soft_wrap=True, highlight=False)

    def begin_tool(self, name: str) -> None:
        self._end_text_line()
        self._spinner_live = Live(
            Spinner("dots", text=f"[yellow]calling tool: {name}…[/]"),
            console=self.console,
            refresh_per_second=12,
            transient=True,
        )
        self._spinner_live.start()

    def end_tool(self, name: str, result: dict) -> None:
        if self._spinner_live is not None:
            self._spinner_live.stop()
            self._spinner_live = None
        is_error = bool(result.get("error"))
        tag = "[red]✗[/]" if is_error else "[green]✓[/]"
        summary = self._summarise(result)
        self.console.print(f"  {tag} [dim]{name}[/]: {summary}")

    def show_error(self, msg: str) -> None:
        self._end_text_line()
        if self._spinner_live is not None:
            self._spinner_live.stop()
            self._spinner_live = None
        self.console.print(f"[red][error][/] {msg}")

    def turn_done(self) -> None:
        self._end_text_line()
        self._has_written_text = False

    def cancelled(self) -> None:
        self._end_text_line()
        if self._spinner_live is not None:
            self._spinner_live.stop()
            self._spinner_live = None
        self.console.print("[yellow][cancelled][/]")

    def _end_text_line(self) -> None:
        if self._has_written_text:
            self.console.print()  # newline
            self._has_written_text = False

    def _summarise(self, result: dict) -> str:
        s = json.dumps(result, ensure_ascii=False)
        return s if len(s) <= 200 else s[:197] + "..."
```

- [ ] **Step 3: Commit**

```bash
git add src/elyos_chat/cli/__init__.py src/elyos_chat/cli/renderer.py
git commit -m "Add Rich-based event renderer with inline streaming and tool spinner"
```

---

## Task 17: Config

**Files:**
- Create: `src/elyos_chat/config.py`

- [ ] **Step 1: Create `src/elyos_chat/config.py`**

```python
"""Environment-based configuration.

Reads ELYOS_PROVIDER, ELYOS_MODEL, ELYOS_API_BASE, ELYOS_API_KEY, plus
the provider-specific key. Fails fast with a clear message.
"""
from __future__ import annotations
import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    provider: str
    model: str | None
    api_base: str
    api_key: str

    @classmethod
    def from_env(cls) -> "Config":
        provider = os.environ.get("ELYOS_PROVIDER", "anthropic").lower()
        model = os.environ.get("ELYOS_MODEL") or None
        api_base = os.environ.get(
            "ELYOS_API_BASE",
            "https://elyos-interview-907656039105.europe-west2.run.app",
        )
        api_key = os.environ.get("ELYOS_API_KEY")
        if not api_key:
            _fail("ELYOS_API_KEY is not set. Copy .env.example to .env and fill it in.")

        # Validate the provider's own key is present.
        required = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }
        if provider not in required:
            _fail(f"Unknown ELYOS_PROVIDER='{provider}'. Use one of: anthropic, openai, gemini.")
        if not os.environ.get(required[provider]):
            _fail(f"ELYOS_PROVIDER={provider} requires {required[provider]} to be set.")

        return cls(provider=provider, model=model, api_base=api_base, api_key=api_key)


def _fail(msg: str) -> None:
    print(f"config error: {msg}", file=sys.stderr)
    sys.exit(2)
```

- [ ] **Step 2: Commit**

```bash
git add src/elyos_chat/config.py
git commit -m "Add env-based Config with fail-fast validation"
```

---

## Task 18: CLI app — entrypoint, SIGINT handler, input loop

**Files:**
- Create: `src/elyos_chat/cli/app.py`

This wires everything together. No tests — manual smoke verification in Task 20.

- [ ] **Step 1: Create `src/elyos_chat/cli/app.py`**

```python
"""CLI entrypoint: input loop, SIGINT handler, provider/tool wiring."""
from __future__ import annotations
import argparse
import asyncio
import signal
import time
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console

from elyos_chat.chat.history import History
from elyos_chat.chat.session import ChatSession
from elyos_chat.cli.renderer import Renderer
from elyos_chat.config import Config
from elyos_chat.tools.http import ToolHttpClient
from elyos_chat.tools.registry import ToolRegistry
from elyos_chat.tools.research import RESEARCH_TOOL
from elyos_chat.tools.weather import WEATHER_TOOL


HISTORY_DIR = Path.home() / ".elyos_chat" / "sessions"
DEFAULT_SYSTEM = (
    "You are a helpful assistant. You have two tools: weather (fast) and "
    "research (slow, 3-8s). Prefer calling tools when the user asks about "
    "real-world facts. Tool errors are returned as JSON with 'error' and "
    "'guidance' fields — read them and decide how to proceed."
)


def _build_provider(cfg: Config):
    if cfg.provider == "anthropic":
        from elyos_chat.providers.anthropic import AnthropicProvider
        return AnthropicProvider(model=cfg.model)
    if cfg.provider == "openai":
        from elyos_chat.providers.openai import OpenAIProvider
        return OpenAIProvider(model=cfg.model)
    if cfg.provider == "gemini":
        from elyos_chat.providers.gemini import GeminiProvider
        return GeminiProvider(model=cfg.model)
    raise SystemExit(f"unsupported provider: {cfg.provider}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="elyos-chat", description="Streaming CLI chat with Elyos tools.")
    p.add_argument("--provider", help="Override ELYOS_PROVIDER (anthropic|openai|gemini)")
    p.add_argument("--model", help="Override ELYOS_MODEL")
    p.add_argument("--resume", help="Resume a session by id, or 'last' for the most recent")
    p.add_argument("--system", help="Path to a system-prompt file")
    return p.parse_args(argv)


async def _amain(args: argparse.Namespace) -> int:
    console = Console()
    cfg = Config.from_env()
    if args.provider:
        cfg.provider = args.provider
    if args.model:
        cfg.model = args.model

    system = DEFAULT_SYSTEM
    if args.system:
        system = Path(args.system).read_text()

    provider = _build_provider(cfg)
    http = ToolHttpClient(base_url=cfg.api_base, api_key=cfg.api_key)
    registry = ToolRegistry(http=http)
    registry.register(WEATHER_TOOL)
    registry.register(RESEARCH_TOOL)

    if args.resume == "last":
        history = History.resume_last(HISTORY_DIR) or History.new(HISTORY_DIR)
    elif args.resume:
        history = History.resume(HISTORY_DIR, args.resume)
    else:
        history = History.new(HISTORY_DIR)

    renderer = Renderer(console=console)
    session = ChatSession(provider=provider, registry=registry,
                          history=history, renderer=renderer, system=system)

    console.print(f"[dim]elyos-chat — provider={cfg.provider} model={provider.model} session={history.session_id}[/]")
    console.print("[dim]Ctrl+C cancels a running turn. Two Ctrl+Cs at the prompt within 2s exits.[/]\n")

    loop = asyncio.get_running_loop()
    last_sigint = {"t": 0.0}

    def on_sigint():
        # If a turn is in flight, cancel it. Otherwise, double-tap to exit.
        if session._cancel is not None:
            session.cancel_current()
            renderer.cancelled()
        else:
            now = time.monotonic()
            if now - last_sigint["t"] < 2.0:
                console.print("[dim]bye[/]")
                loop.stop()
            else:
                console.print("[dim]Press Ctrl+C again within 2s to exit.[/]")
                last_sigint["t"] = now

    loop.add_signal_handler(signal.SIGINT, on_sigint)

    prompt = PromptSession()
    try:
        with patch_stdout():
            while True:
                try:
                    text = await prompt.prompt_async("you> ")
                except (EOFError, KeyboardInterrupt):
                    break
                if not text.strip():
                    continue
                if text.strip() in {"/exit", "/quit"}:
                    break
                await session.handle_user_input(text.strip())
    finally:
        await http.aclose()
    return 0


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_amain(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add src/elyos_chat/cli/app.py
git commit -m "Add CLI entrypoint with SIGINT handler and prompt_toolkit input loop"
```

---

## Task 19: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Elyos CLI Chat

A streaming command-line chat app that calls an LLM (Claude / OpenAI / Gemini)
with two tools — weather (fast) and research (slow, 3–8s) — against the
Elyos interview API.

## Features

- Streaming responses (token-by-token).
- Tool calling with a pending-state spinner.
- Graceful `Ctrl+C` cancellation: cancels the current turn, returns to the
  prompt. Two `Ctrl+C`s within 2 seconds at the prompt exits cleanly.
- Conversation history persisted to `~/.elyos_chat/sessions/*.jsonl`.
  Resume with `--resume last` or `--resume <session-id>`.
- Three LLM providers selectable via `ELYOS_PROVIDER`.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

cp .env.example .env
# Edit .env — set ELYOS_API_KEY, ELYOS_PROVIDER, and the matching provider key.
```

## Usage

```bash
python -m elyos_chat                                  # start a new session
python -m elyos_chat --resume last                    # resume the newest session
python -m elyos_chat --provider gemini --model gemini-2.0-flash
```

## Tests

```bash
pytest -v
```

## API quirks

See [`docs/api-findings.md`](docs/api-findings.md). The probe script that
generated them lives at `scripts/probe_api.py`.

## Design

See [`docs/superpowers/specs/2026-05-14-elyos-chat-design.md`](docs/superpowers/specs/2026-05-14-elyos-chat-design.md).

## Project layout

```
src/elyos_chat/
  cli/         input loop, rendering, signal handling
  chat/        ChatSession orchestrator, History, CancelToken, Events
  providers/   Provider Protocol + anthropic, openai, gemini adapters
  tools/       registry, HTTP client, weather, research
  config.py    env-based config
scripts/
  probe_api.py systematic API quirk probes
tests/         four smoke test files + FakeProvider fixture
docs/          spec, plan, API findings
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Add README with setup, usage, tests, and project layout"
```

---

## Task 20: Full test pass + manual smoke

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

```bash
pytest -v
```

Expected: ~17 passed (4 in `test_cancel_token`, 5 in `test_history`, 7 in `test_http_retry`, 1 in `test_cancel`, 4 in `test_session_tool_loop`).

If any fail, stop and fix before continuing. Use `superpowers:systematic-debugging` if a failure is unclear.

- [ ] **Step 2: Run the app against each provider manually**

For each provider in `anthropic`, `openai`, `gemini`:

```bash
# 1. Set the env
export ELYOS_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# 2. Start a session
python -m elyos_chat
```

Run these scenarios per provider and note results:

| Scenario | What to type | Expected |
|---|---|---|
| Pure text | "What is 2+2?" | Streamed text answer, no tools, returns to prompt. |
| Weather | "What's the weather in London?" | Spinner briefly, `✓ weather: {...}` line, then streamed answer. |
| Research | "Research solar energy briefly." | Spinner visible for 3-8s, then `✓ research: {...}`, then answer. |
| Cancel mid-research | Same as above; press Ctrl+C while spinner is up | `[cancelled]`, returns to prompt, app still running. |
| Two tools in a turn | "Weather in Tokyo AND research CRISPR briefly." | Two tool calls, ideally in parallel (overall wall ≈ max not sum). |
| Resume | Exit, then `python -m elyos_chat --resume last` and type "what did I ask before?" | Model has prior context. |

- [ ] **Step 3: Inspect a session JSONL**

```bash
ls ~/.elyos_chat/sessions/
cat ~/.elyos_chat/sessions/<latest>.jsonl | head -20
```

Expected: one JSON object per line, with `role` of user / assistant / tool, and `tool_calls` / `tool_results` populated correctly.

- [ ] **Step 4: Commit any final tweaks**

If anything needed adjusting during manual smoke, commit those tweaks with messages like `Fix: <specific issue>`.

---

## Task 21: Loom video prep checklist

**Files:** none (preparation only)

- [ ] **Step 1: Verify the deliverables checklist in the spec is complete**

Open `docs/superpowers/specs/2026-05-14-elyos-chat-design.md`, scroll to "Deliverables checklist". Tick off each item or note what's missing.

- [ ] **Step 2: Rehearse the five Loom segments**

Outline notes (not a script):

1. **Demo (3–4 min)** — Start the app. Show one weather query, one research query with the spinner, one mid-research cancel. Briefly show `--resume last`.
2. **API discovery (3–4 min)** — *most important.* Walk `docs/api-findings.md` from top to bottom. For each finding: what surprised you, the repro, why your handler is shaped the way it is.
3. **Code walkthrough (3–4 min)** — Open `chat/session.py` (the loop), then `providers/base.py` + one adapter (show the event normalization seam), then `chat/cancel.py` + the SIGINT handler in `cli/app.py`.
4. **Trade-offs (2–3 min)** — Three providers vs. line budget. Minimal tests vs. live-API tests. JSONL vs. SQLite for history. Cooperative cancel vs. task cancellation.
5. **Self-critique (1–2 min)** — What you'd add with more time (e.g. integration tests, structured telemetry, better resume UX, real retry-after parsing for HTTP dates). What feels weakest.

- [ ] **Step 3: Bundle the submission**

```bash
# Make sure everything's committed.
git status

# Tag the submission.
git tag -a submission-v1 -m "Initial submission"

# Optionally: zip excluding venv, .env, history.
zip -r elyos-chat-submission.zip . \
  -x ".venv/*" -x ".git/*" -x ".env" -x ".pytest_cache/*" \
  -x "__pycache__/*" -x "*/__pycache__/*"
```

- [ ] **Step 4: Final mental check — does the submission tell the story?**

The reviewers said the things they *don't* want are: "didn't test the APIs beyond happy path", "can't explain their own code", "blames the API for issues instead of handling them", "defensive when discussing trade-offs or weaknesses". Verify:

- The probe script + findings doc prove you went past happy path.
- You can walk anyone through the chat loop, the cancellation flow, and one provider adapter without reading the code.
- Every quirk has a handler with a finding-ID comment — not "this API is broken" in commit messages.
- Trade-offs and weaknesses have their own Loom section, addressed openly.

---

## Self-review (run after the plan is written)

This section is a checklist run after writing the plan. Issues found are fixed inline; this section stays as the running summary.

**1. Spec coverage**

| Spec requirement | Covered by |
|---|---|
| Accept user text input | Task 18 (`prompt_toolkit` loop in `cli/app.py`) |
| Stream LLM responses | Tasks 11–13 (provider adapters) + Task 16 (renderer) |
| Tool calling — weather + research | Tasks 6–7 (registry + handlers) + Task 14 (session loop) |
| Pending state during slow operations | Task 16 (renderer spinner) |
| Cancellation via Ctrl+C, graceful | Tasks 3, 15, 18 (CancelToken, session test, SIGINT handler) |
| Conversation history persistence | Task 4 (JSONL) + Task 18 (`--resume`) |
| Handle APIs gracefully | Tasks 5, 7, 8, 9 (HTTP retry, handlers, probe, findings) |
| Three providers env-selectable | Tasks 10–13 + Task 17 (config) + Task 18 (provider build) |
| Smoke tests | Tasks 3, 4, 5, 14, 15 |
| README + findings doc | Tasks 9, 19 |
| Loom prep | Task 21 |
| MAX_TOOL_ITERATIONS guard | Task 14 (`max_tool_iterations` parameter, test included) |

**2. Placeholder scan** — Searched for TBD / TODO / "implement later" / "fill in" / "appropriate error handling". One legitimate `<...>` template appears in `docs/api-findings.md` (Task 9 step 1) because the contents depend on real probe output; the surrounding step explicitly tells the engineer to replace `<...>` with observed values.

**3. Type consistency** — Spot-checked:
- `Turn` fields used across `history.py`, `session.py`, and each adapter: `role`, `content`, `tool_calls`, `tool_results`, `cancelled`, `ts`. Consistent.
- `Result[T]` interface (`is_ok`, `is_err`, `value`, `error`, `is_transient`) used in `http.py`, `weather.py`, `research.py`. Consistent.
- Event types (`TextDelta.text`, `ToolUseEnd.{tool_use_id,name,args}`, `TurnEnd.reason`) used identically across providers and `session.py`. Consistent.
- `ChatSession.cancel_current()` — defined in Task 14, used in Tasks 15 and 18. Consistent.
- `Renderer` Protocol methods (`write`, `begin_tool`, `end_tool`, `show_error`, `turn_done`, `cancelled`) — defined in Task 14, implemented in Task 16, stubbed in test renderers (Tasks 14 & 15). The `cancelled()` method is implemented in Task 16's `Renderer` and called from `cli/app.py` SIGINT handler in Task 18; not part of the `Renderer` Protocol in `session.py` because the session never calls it. Consistent.
