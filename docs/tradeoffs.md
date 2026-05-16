# Trade-offs

Three decisions in this codebase have meaningful trade-offs. The cancellation model is
the most consequential; the other two are smaller but worth naming.

---

## Cooperative cancellation vs. `asyncio.CancelledError`

**The decision.** I built a `CancelToken` (an `asyncio.Event` wrapper) and polled it
explicitly at specific points — in the provider stream loop, in the HTTP retry loop,
between tool dispatches. When the user presses Esc, the token's event flips, and every
layer notices on its next poll.

**The alternative I considered.** Asyncio gives you task cancellation for free.
`task.cancel()` raises `CancelledError` at any `await` point in the task. I could have
wrapped the chat session's run loop in a single task, called `task.cancel()` on Esc, and
let `CancelledError` propagate up. Far less code — no token to thread through, no
polling points to remember.

**Why I went the harder route.** Predictable cleanup. The chat session does a few things
that must not be interrupted partway through:

- Appending a turn to the JSONL history file. The write is one line, but it's two
  operations: write the bytes, write the newline. A `CancelledError` between them
  corrupts the file in a way that's hard to detect on resume.
- Writing the final tool result to the websocket. If the user cancels after the tool
  finishes but before the result is sent, the LLM's next turn sees the tool call without
  a result and gets confused.
- Closing the HTTP connection cleanly. Mid-request cancel via `CancelledError` leaks the
  connection until the pool reaps it.

With cooperative cancellation, I know exactly where cancellation can land: between
events in the stream loop, between retries in the HTTP client, between tool dispatches.
None of those boundaries are mid-write. Cleanup is guaranteed.

**What it costs.** Discipline. Every new long-running operation has to remember to poll
the token, or it isn't cancellable. If I add a fourth tool that does a multi-step API
call internally, that tool has to thread the token through its own steps. There's no
compiler help — it's a convention, and conventions rot.

A secondary cost is responsiveness. The lag between Esc and the actual cancel is bounded
by the *gap between polls*. In practice that's milliseconds (the LLM stream emits events
faster than that, and the HTTP backoff has a `wait_for` that's interruptible). But in
principle a poorly-instrumented long-running operation could ignore Esc for seconds.

**How I'd mitigate that cost with more time.** A `@cancellable` decorator on
long-running coroutines that auto-polls the active token between operations. Or, more
radically, a context-local token that all helpers read from automatically, so individual
coroutines don't have to thread it explicitly. Both are more elegant than what I built,
but neither were needed for the assignment's scope.

The codebase is small (three polling points in hot paths), the cost of discipline is low
at this size, and the upside — never having to think about "what state was I in when
`CancelledError` fired?" — is exactly the property I want when the worst-case is corrupt
session history.

---

## Per-tool normalisation vs. HTTP-client normalisation

**The decision.** API quirks (soft-throttle, schema variation, staleness) are normalised
inside each *tool handler* — `tools/weather.py::_normalise`,
`tools/research.py::_normalise` — not inside the shared HTTP client.

**The alternative I considered.** Putting the normalisation in `ToolHttpClient.get()`.
Less duplication if the throttle shape is identical across endpoints (which it is). One
place to fix if the API changes.

**Why I went the per-tool route.** The HTTP client should stay content-agnostic. It
knows about transport — status codes, retries, timeouts, headers. It should not know
that a `200` with `status: throttled` is conceptually a `429`, because that
interpretation is *Elyos-specific*. If we later add a tool that calls a different API
(say, an internal RAG endpoint), the HTTP client should be reusable without inheriting
Elyos's quirks.

**What it costs.** Some duplication. `weather.py::_normalise` and
`research.py::_normalise` both have a few lines detecting `status == "throttled"`. If I
add a fifth Elyos tool, I'd write those lines a fifth time. A shared helper
(`elyos_quirks.detect_soft_throttle()`) would solve that without re-coupling the HTTP
layer.

---

## JSONL history file vs. SQLite

**The decision.** Conversation history is a `*.jsonl` file per session in
`~/.elyos_chat/sessions/`. One turn per line, appended with `flush()`. Resume reads
lines back into memory.

**The alternative I considered.** SQLite with a `turns` table.

**Why I went JSONL.** Greppable. No schema migrations. Trivially debuggable — `cat`,
`jq`, `wc -l`. For a chat client that's mostly append-only and read-once-on-resume, the
ergonomics win.

**What it costs.** No querying (can't find "every session where the model called the
research tool"). No concurrent writes (two `ChatSession`s on the same file race). No
schema evolution — if I change `Turn.to_jsonl()`, old sessions break on resume. The
fragility around schema changes is the part I'd fix first: a `version:` field per line
plus a small migration on load.
