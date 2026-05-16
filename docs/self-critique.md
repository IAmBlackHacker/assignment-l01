# Self-Critique

## Weakest parts

### History persistence is fragile

Conversation history is JSONL with no schema version. `Turn.to_jsonl()` writes whatever
shape `Turn` happens to have right now. If I ever change that shape — add a field,
rename one, change a tool result's structure — every existing session breaks on resume.
There's no migration path, no version negotiation, no fallback to "skip this line and
log a warning".

It's the part that would bite first in production. The fix is small — a `version: N`
field per line plus a `migrate(version, dict) -> Turn` function — but I didn't do it
because the assignment is single-session and the resume code path is only one of
several smoke tests.

### The provider abstraction leaks at the conversation-replay boundary

Each of `providers/anthropic.py`, `openai.py`, `gemini.py` reimplements the conversion
from my internal `Turn` objects to the provider's expected message shape. The shapes are
all similar (system, user, assistant, tool calls, tool results) but differ in subtle
ways — Anthropic's tool result has a `tool_use_id`, OpenAI's has a `tool_call_id` and
expects the role to be `"tool"`, Gemini wraps tool calls in `function_call` parts.

I have three slightly-different implementations of the same translation. If I add a
fourth provider, I write that translation a fourth time. A canonical intermediate
format (my `Turn` already is one) with one provider-specific encoder per SDK would be
cleaner, and would also make the test surface smaller (right now I'd have to test each
provider's replay logic separately).

### No frontend integration tests

I have `store.test.ts` for the reducer. Nothing asserts that the rendered tool spinner
appears within X ms of a `tool_use_start` event, or that pressing Esc on `window`
actually triggers `textWs.cancel()`. The Escape-cancel bug I caught during demo prep
(see [`api-discovery.md`](api-discovery.md), "A known bug") is exactly the kind of thing
a Playwright or Vitest-with-jsdom test would have flagged immediately — keyboard event
on disabled element, handler never fires. Manual smoke testing caught it eventually, but
late.

---

## What I'd change with more time

### Continuous schema-drift detection on the Elyos API

The eight quirks I documented in [`api-findings.md`](api-findings.md) are a snapshot of
how the API behaved on 2026-05-14. They could change tomorrow. With more time I'd:

- Wire `scripts/probe_api.py` into CI on a nightly cron.
- Diff the output against a checked-in baseline file.
- Fail the build (or just alert) on schema changes.

This matters because the normalisers in `tools/weather.py::_normalise` and
`tools/research.py::_normalise` are written *against* the specific shapes I observed.
If a new shape appears, my code silently passes it through to the LLM and the LLM does
something unpredictable.

### Threshold-aware staleness warning

Right now `cached: true` → attach a generic `staleness_warning`. If the API ever
returns `cached: true` with a small `cache_age_seconds` (say, 5 minutes), the warning is
scary for no reason. I'd add a threshold (warn only if older than 30 days) and include
the actual age so the model can adjust its tone.

### Consolidate voice and text cancel paths

The voice mode (OpenAI Realtime) has its own cancellation model — it talks directly to
Realtime's server-side VAD and barge-in. My `CancelToken` doesn't reach into that path.
There are effectively two cancellation mechanisms in the codebase, and a user pressing
Esc in voice mode goes through a different code path than the same key in text mode.
Two mechanisms is one too many. With more time I'd find a way to make Esc in voice mode
trigger the same `CancelToken` (or vice versa).

---

## Honest acknowledgments

A few things I didn't get to, in priority order:

- **Tool result schemas aren't versioned.** `weather.py` and `research.py` return
  slightly different shapes (`primary_condition` vs `summary`, `multiple_conditions` vs
  `staleness_warning`). The LLM handles the variation fine, but there's no schema
  contract I could point at. A `tools.ToolResult` typed-dict per tool would help.
- **The HTTP client retries 3 times by default with no per-call override.** A caller
  who wants a fast-fail for a critical-path call has no way to ask for fewer retries.
  The fix is one constructor arg; I just didn't add it.
- **I tested error handling with mocks, not against real API failures.**
  `tests/test_http_retry.py` uses `respx` to inject 429s and 5xxs. That's fine for
  verifying retry logic, but it doesn't catch quirks the real API might have that I
  haven't probed for.
- **I didn't fuzz the API hard.** Tried Unicode, long input, empty, whitespace, and
  unknown extras. Didn't try control characters, very large payloads, injection-shaped
  strings, or unusual content-types. Probably fine for this scope, definitely not fine
  for production.

This is one engineer's first pass on a take-home, not a system that's been
pressure-tested. The weakest parts are the parts that would be obvious if I ran it for
a month — schema drift, persistence migration, integration test coverage. None of them
are fundamental design problems; they're "more time" problems.
