# Elyos CLI Chat — Design Spec

**Date:** 2026-05-14
**Author:** Lokesh (kulkarnim@gmail.com)
**Status:** Approved — ready for implementation plan
**Assignment:** Elyos AI Technical Interview 2.0 (https://gist.github.com/pstrav/c306b3e493d52fab57ca8e64f3516a1b)

---

## 1. Goal

Build a single-process command-line chat app that:

1. Accepts user text input in an interactive loop.
2. Streams LLM responses token-by-token to the terminal.
3. Supports tool calling against two endpoints — `/weather` (fast) and `/research` (3–8s).
4. Shows a clear pending state while a slow tool call is in flight.
5. Cancels the in-flight turn on `Ctrl+C` without exiting the app (second `Ctrl+C` at the prompt exits).
6. Persists conversation history to disk and can resume prior sessions.
7. Handles the documented and undocumented quirks of the Elyos API gracefully.
8. Is comprehensible and extensible — new tools and new LLM providers drop in with localized changes.

Success is judged on three dimensions per the assignment: **implementation quality**, **API discovery & handling**, and **communication** (the Loom video). The design below is shaped around those three.

---

## 2. Decisions (locked in during brainstorming)

| Choice | Selection | Rationale |
|---|---|---|
| Language | Python | Best LLM SDK ergonomics; asyncio fits streaming + cancel naturally. |
| LLM providers | Claude + Gemini + OpenAI, env-selectable, all fully implemented | User asked for `ELYOS_PROVIDER` switchability across all three. |
| CLI | `prompt_toolkit` (input) + `rich` (output, spinner) | Best fit for streaming + cancel + spinner UX. |
| History | In-memory + JSONL on disk at `~/.elyos_chat/sessions/<id>.jsonl` | Satisfies "persistence" literally; trivial to resume. |
| API discovery | Dedicated `scripts/probe_api.py` + `docs/api-findings.md` | Produces the exact evidence the video's "API discovery" segment needs. |
| Testing | Minimal smoke tests, no live-API tests | Per user direction; covers the bug classes most likely to bite. |
| Packaging | `pip` + `requirements.txt` + `venv` | No new tooling for the reviewer. |
| API base URL | `https://elyos-interview-907656039105.europe-west2.run.app` | From assignment gist. |
| API key | `elyos2025` via `ELYOS_API_KEY` env var | From assignment gist; not hardcoded. |

**Scope trade-off explicitly accepted:** The spec's "150–250 lines of focused code" budget assumes one provider. Three provider adapters add ~150–250 lines of event-normalization code, putting total around ~600 lines. This is a deliberate choice — the user prioritized provider extensibility — and will be called out in the Loom "trade-offs" section.

---

## 3. Architecture (Approach A — layered async pipeline with a Provider port)

Six modules, one job each. Sizes are estimates that anchor "is this file doing too much?" judgments.

```
cli/           input loop, rendering, key bindings, spinner
chat/          ChatSession (turn orchestrator), History, CancelToken, Events
providers/     base.py (Protocol) + anthropic.py, openai.py, gemini.py
tools/         registry + http client + weather + research
config.py      env loading, provider selection
```

**Module responsibilities**

- **`cli/app.py`** (~60 lines) — Entrypoint. Parses CLI args (`--provider`, `--model`, `--resume`, `--system`), loads config, constructs `ChatSession`, runs the input/output loop, installs the SIGINT handler. Owns `rich.Console` and the `prompt_toolkit` `PromptSession`.
- **`cli/renderer.py`** (~50 lines) — Converts the normalized event stream into terminal output: streams `TextDelta` into a live region, shows a `rich.Spinner` during tool calls, prints tool name + truncated args/result above the spinner. No business logic.
- **`chat/session.py`** (~80 lines) — Orchestrates a turn: calls `Provider.stream_turn`, fans events to the renderer, dispatches tool calls via the registry, appends results to history, loops until the model produces a final answer. Owns the per-turn `CancelToken`.
- **`chat/history.py`** (~40 lines) — Append-only turn log with two operations: `append(turn)` and `snapshot()`. Persists each turn as one JSONL line; `--resume` rehydrates by replay.
- **`chat/events.py`** (~30 lines) — Canonical event dataclasses: `TextDelta`, `ToolUseStart`, `ToolUseArgsDelta`, `ToolUseEnd`, `TurnEnd`, `Error`. Provider-agnostic.
- **`chat/cancel.py`** (~15 lines) — `CancelToken` (an `asyncio.Event` wrapper).
- **`providers/base.py`** (~50 lines) — `Provider` Protocol with one method: `stream_turn(messages, tools, cancel) -> AsyncIterator[Event]`.
- **`providers/{anthropic,openai,gemini}.py`** (~80 lines each) — SDK-specific. Translate canonical messages → SDK call; translate SDK stream events → canonical events. Tool-schema translation also lives here.
- **`tools/registry.py`** (~30 lines) — Tool name → callable + canonical JSON schema. Exposes `for_provider(provider_name)` to emit provider-specific tool definitions.
- **`tools/http.py`** (~40 lines) — Single shared `httpx.AsyncClient` with base URL + `X-API-Key` header, timeouts, retry/backoff. Returns `Result[T]` — never raises out.
- **`tools/weather.py`, `tools/research.py`** (~40 lines each) — Validate args, call the HTTP client, normalize quirks (referencing finding IDs from `docs/api-findings.md` in comments).
- **`config.py`** (~25 lines) — Reads `ELYOS_PROVIDER`, `ELYOS_MODEL`, `ELYOS_API_KEY`, `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY`. Fails fast with a clear message if the selected provider's key is missing.

**Why this shape**

- The `Provider` Protocol's event stream is the **only** seam between the chat loop and the SDKs. The chat loop is provider-agnostic and unit-testable with a `FakeProvider` that yields scripted events.
- Tools are looked up by name from a registry — adding a tool is one new file + one line in `registry.py`.
- The HTTP layer is the chokepoint for all transport errors, so retry/backoff/timeout policy lives in one place.

---

## 4. Data flow per turn

A turn begins on `Enter` and ends when the assistant produces a final answer (after zero or more tool calls).

```
User types text
      │
      ▼
ChatSession.handle_user_input(text)
  history.append(user_turn)
  loop:
      events = provider.stream_turn(history.snapshot(), tools, cancel)
      pending_tool_calls = []
      async for ev in events:
          match ev:
              TextDelta(t)        → renderer.write(t)
              ToolUseStart(id,n)  → renderer.begin_tool(n)   # spinner on
              ToolUseArgsDelta(d) → accumulate JSON fragment
              ToolUseEnd(id,n,a)  → pending_tool_calls.append(...)
              TurnEnd(reason)     → break
              Error(e)            → surface to renderer
      history.append(assistant_turn(text, pending_tool_calls))
      if not pending_tool_calls:
          return                                 # turn complete
      results = await asyncio.gather(*[
          tools.dispatch(tc.name, tc.args, cancel) for tc in pending_tool_calls
      ], return_exceptions=True)
      history.append(tool_results_turn(results))
      # loop back: feed results to provider for the follow-up
```

**Key choices**

- **Event-shaped provider abstraction, not response-shaped.** Each provider yields the same five event types regardless of SDK; per-provider translation cost is paid once per adapter.
- **Tool args are streamed.** Anthropic and OpenAI stream JSON fragments; we buffer per tool-use id and only dispatch on `ToolUseEnd`. Gemini delivers args atomically; the adapter still emits one `ToolUseArgsDelta` then `ToolUseEnd` for shape parity.
- **Parallel tool dispatch.** When the model returns >1 tool use in a turn, we run them concurrently via `asyncio.gather`. Matters because `research` is 3–8s.
- **History snapshot is per-call, immutable.** The provider receives a snapshot, not a mutable reference.
- **History is always coherent on disk.** Tool calls and tool results are persisted as separate JSONL records, in order. Resume rebuilds in-memory state by replay.

**JSONL turn shapes**

```json
{"role":"user","content":"...","ts":...}
{"role":"assistant","content":"...","tool_calls":[{"id":"...","name":"weather","args":{...}}],"ts":...}
{"role":"tool","results":[{"id":"...","content":"...","is_error":false}],"ts":...}
{"role":"assistant","content":"final answer","tool_calls":[],"ts":...}
```

One JSON object per line; flush after each `append`.

---

## 5. Cancellation model

**Primitive**

```python
@dataclass
class CancelToken:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    def cancel(self):       self.event.set()
    def cancelled(self):    return self.event.is_set()
    async def wait(self):   await self.event.wait()
```

One token per turn, threaded into `provider.stream_turn(..., cancel=token)` and `tools.dispatch(..., cancel=token)`. Cooperative — providers and tools race their own awaitables against `cancel.wait()`.

**SIGINT handler state table**

| State when Ctrl+C arrives | Action |
|---|---|
| Provider streaming or tool in-flight | `cancel.cancel()` — current turn unwinds, prompt returns. Renderer prints `[cancelled]`. |
| At input prompt, no turn in flight | Print "Press Ctrl+C again to exit." Arm 2-second exit window. |
| Second Ctrl+C within 2s at prompt | Clean shutdown: close `httpx.AsyncClient`, flush JSONL, exit 0. |

Installed via `loop.add_signal_handler(signal.SIGINT, on_sigint)` — not via `KeyboardInterrupt`, which interacts badly with `prompt_toolkit`'s SIGINT semantics.

**How each layer cooperates**

- **Provider stream:** SDK call wrapped in `asyncio.wait` against `cancel.wait()`. On cancel, we close the SDK stream (`stream.close()` / `aclose()`) and stop yielding. We translate SDK cancellation exceptions into a clean `TurnEnd(reason="cancelled")` event — we do not let them propagate.
- **Tool dispatch:** tool coroutine races against `cancel.wait()`. The `httpx` request itself is cancellable; cancelling the wrapping task closes the underlying TCP connection.
- **Parallel tool gather:** cancelling one sibling cancels all (`asyncio.gather` propagates cancellation). `return_exceptions=True` keeps the loop alive.
- **Mid-tool cancellation:** still append a `tool` turn with `{is_error: true, content: "cancelled by user"}` so history stays coherent — the model has context if the user types something new on the next turn.

**Explicit non-goals**

- Cancel ≠ exit. Cancel cancels a *turn*.
- Cancel ≠ retry. Cancellation is intent; retry is for transient failure.
- We do not reverse partial streamed output already shown. The truncated assistant turn is recorded with whatever streamed so far, plus `cancelled: true`.

---

## 6. Error handling & API quirk strategy

Two layers, with the rule that **tools always return something the model can read** — a failure becomes `{"error": "...", "guidance": "..."}` rather than a Python exception that kills the turn.

```
┌─────────────────────────────────────────────┐
│  Layer 1 — tools/http.py (transport)        │
│  timeouts, retries, network errors, status, │
│  JSON validity. Returns Result[T].          │
└────────────────────┬────────────────────────┘
                     │
┌────────────────────▼────────────────────────┐
│  Layer 2 — tools/weather.py, research.py    │
│  arg validation, schema validation,         │
│  known-quirk normalization. Returns dict.   │
└─────────────────────────────────────────────┘
```

**`tools/http.py` retry policy**

- Retry on: 429, 502, 503, 504, `ReadTimeout`, `ConnectError`.
- Backoff: `250ms · 2^n + jitter`, max 3 attempts.
- Honor `Retry-After` if present.
- Abort early on `cancel.cancelled()`.
- Content-type guard: non-JSON body → `Result.err("non-json:<excerpt>")`.
- 4xx that aren't 429 → no retry; surfaced as error to the tool.

Total per-tool budget capped at ~30s so the model can decide what to do when the API is wedged.

**Quirk pipeline**

```
scripts/probe_api.py  →  docs/api-findings.md  →  tools/{weather,research}.py
   (probes)               (one row per quirk)        (handlers reference finding IDs)
```

**`scripts/probe_api.py` categories**

- **Auth** — missing key, wrong key, header case sensitivity (`x-api-key` vs `X-API-Key`).
- **Param surface** — missing required, empty string, very long string, unicode, URL-encoded vs raw spaces, leading/trailing whitespace, repeated query params, unknown extra params.
- **Determinism** — 3× same `location`, 3× same `topic`: identical body? Latency variance?
- **Timing** — p50/p95/p99 for both endpoints; does `research` ever return <1s (cached?) or >10s (degraded?)
- **Response shape** — field stability, nulls, prose-in-fields, JSON validity every time.
- **Status-code semantics** — does the API use 200 for success only, or also for soft errors with `error` in body?
- **Concurrency** — 10 parallel `research` calls: rate limit? Coalesced? Out-of-order completion?

**Finding format** (`docs/api-findings.md`)

```
### F-03: research endpoint returns 200 with {"error": "..."} for empty topic
- Repro: curl -H "X-API-Key: $ELYOS_API_KEY" \
    "https://.../research?topic="
- Observed: HTTP 200, body: {"error": "topic required"}
- Impact: must treat 200 as success only when expected schema present.
- Handler: tools/research.py — schema_guard()
```

**Tool handler shape** (illustrative — `tools/research.py`)

```python
async def research(args: dict, cancel: CancelToken, http: ToolHttpClient) -> dict:
    topic = (args.get("topic") or "").strip()
    if not topic:
        return {"error": "missing topic",
                "guidance": "ask the user for a research topic"}
    result = await http.get("/research", {"topic": topic}, cancel)
    if result.is_err:
        return {"error": result.error, "transient": result.is_transient}
    return _normalise(result.value)   # quirk handlers reference finding IDs
```

**LLM-side errors** (rate limits, malformed tool args from the model) are caught in the provider adapter and surfaced as `Event.Error`, which the renderer prints cleanly and offers the user a chance to retry.

**Explicit non-goals**

- No circuit breaker. Three retries with jittered backoff is enough for a 1-week assignment.
- No persistent retry queue. Terminal failures are user-visible; the user decides next step.
- No automatic schema-drift detection. Handlers fail loudly with a clear message if the API changes shape.

---

## 7. File layout

```
elyos-assignment/
├── README.md                       # setup, usage, design summary, quirks summary
├── requirements.txt                # anthropic, openai, google-genai, httpx,
│                                   # prompt_toolkit, rich, python-dotenv, pytest, respx
├── .env.example                    # ELYOS_API_KEY, ELYOS_PROVIDER, *_API_KEY vars
├── .gitignore                      # .venv, .env, __pycache__, ~/.elyos_chat
├── pyproject.toml                  # minimal — just to enable `python -m elyos_chat`
│
├── src/elyos_chat/
│   ├── __main__.py                 # python -m elyos_chat
│   ├── config.py
│   ├── cli/
│   │   ├── app.py
│   │   └── renderer.py
│   ├── chat/
│   │   ├── session.py
│   │   ├── history.py
│   │   ├── events.py
│   │   └── cancel.py
│   ├── providers/
│   │   ├── base.py
│   │   ├── anthropic.py
│   │   ├── openai.py
│   │   └── gemini.py
│   └── tools/
│       ├── registry.py
│       ├── http.py
│       ├── weather.py
│       └── research.py
│
├── scripts/
│   └── probe_api.py
│
├── tests/
│   ├── conftest.py                 # FakeProvider, respx fixtures
│   ├── test_history.py
│   ├── test_cancel.py
│   ├── test_http_retry.py
│   └── test_session_tool_loop.py
│
└── docs/
    ├── api-findings.md             # one row per quirk
    └── superpowers/specs/
        └── 2026-05-14-elyos-chat-design.md
```

**Tool-schema translation** — each provider wants a slightly different JSON Schema shape (Anthropic: `input_schema`; OpenAI: `parameters` inside `function`; Gemini: `function_declarations`). `tools/registry.py` keeps **one canonical schema per tool** and exposes `for_provider(name)` that emits the right shape. Adding a provider = one mapping function; adding a tool = one schema definition.

---

## 8. Testing — minimal smoke tests, the right ones

Five files. None hit the real API. The `FakeProvider` + `respx` HTTP mock cover the seams that matter.

| Test file | Asserts |
|---|---|
| `test_history.py` | `append → snapshot` consistent; JSONL roundtrips byte-for-byte after replay; `--resume last` picks the newest session. |
| `test_cancel.py` | `CancelToken.cancel()` mid-stream causes the chat loop to exit; renderer prints `[cancelled]`; history records the truncated assistant turn with `cancelled: true`. |
| `test_http_retry.py` | 503 → retried up to 3× with backoff; non-JSON body → `Result.err("non-json:...")`; `Retry-After` honored; cancel during retry exits cleanly. |
| `test_session_tool_loop.py` | `FakeProvider` yields `ToolUseEnd("weather", {...})` then `TurnEnd`. Asserts `tools.dispatch` called, result appended, provider re-invoked with the tool result in history. |
| `conftest.py` | `FakeProvider(scripted_events)` + `respx` fixture. Anything tricky should be expressible as "scripted events in, asserted history out." |

**Deliberately out of scope** — live-API integration tests, per-provider end-to-end tests (the seam is covered by `FakeProvider`; per-provider adapters are validated manually + via the probe script).

---

## 9. Deliverables checklist (assignment)

- [ ] Working CLI: streaming, both tools, pending state, cancel, history persistence.
- [ ] Three provider adapters, env-selectable.
- [ ] `scripts/probe_api.py` + `docs/api-findings.md` documenting discovered quirks.
- [ ] Smoke tests passing.
- [ ] `README.md` with setup, usage, design summary, link to findings.
- [ ] Loom video (10–15 min) with the five required sections — emphasis on API discovery.
- [ ] AI assistant session transcript bundled with submission.

---

## 10. Extension points (where future work lands cleanly)

- **New tool** — one file in `tools/` + one line in `tools/registry.py`. Canonical schema is auto-translated for all providers.
- **New LLM provider** — one file in `providers/`. Implement the `Provider` Protocol; the chat loop is unchanged.
- **Persistent backend swap** — `chat/history.py` is the only place that knows about JSONL. Replace with SQLite or Postgres behind the same `append`/`snapshot` interface.
- **Observability** — `chat/events.py` is already a structured stream; wiring an OpenTelemetry exporter to the event bus is additive.
- **Voice / non-CLI front-ends** — `chat/session.py` does not depend on `cli/`. A different front-end can drive the same orchestrator.

---

## 11. Open risks

| Risk | Mitigation |
|---|---|
| Line budget overrun from three providers | Acknowledged trade-off; called out in Loom "trade-offs" section. |
| `prompt_toolkit` + SIGINT + asyncio interactions are fiddly | Use `loop.add_signal_handler` rather than `KeyboardInterrupt`; cover with `test_cancel.py`. |
| Gemini SDK's tool-streaming semantics differ from Anthropic/OpenAI | Adapter normalizes; if Gemini's API forces atomic args, we still emit synthetic `ToolUseArgsDelta` for shape parity. |
| Real API quirks may exceed what the probe predicts | Handlers reference finding IDs; new findings → add row, add handler, no architectural change. |
| Time pressure (1 week) | Strict YAGNI on testing, observability, and packaging; scope is locked above. |
