# API Discovery (3–4 min)

> The most important section. Goal is to show *how I thought*, not to recite a polished list.

The full technical reference for every quirk lives in [`api-findings.md`](api-findings.md).
This document is the narrative companion — what I observed, how I figured it out, how I
reasoned about handling it, and what I'm still unsure about.

---

## What I observed that wasn't in the documentation

The Elyos API has two endpoints, `/weather` and `/research`. The documented contract is
straightforward — pass a `location` or `topic`, get a JSON body back. The undocumented
behaviour is where most of the work was. Eight findings, ordered roughly by how much they
would have broken a naïve client:

1. **Soft throttling via HTTP 200.** Rate-limited responses come back as `200 OK` with a
   body like `{"status":"throttled", "retry_after_seconds":27, "data":null}`. A naïve HTTP
   client treats this as success and hands the empty body to the model.
2. **Non-deterministic weather response shape.** The same location returns two different
   schemas across calls — sometimes flat (`temperature_c`, `condition`, `humidity` at top
   level), sometimes wrapped in a `conditions` array with `note: "Multiple conditions
   reported"`. London returned both shapes in different probe runs.
3. **Silent stale cache on `/research`.** Obscure or empty topics return content from
   March 2024 (`cache_age_seconds: 26784000` ≈ 310 days) — flagged only by an extra
   `"cached": true` field. Well-known topics like "solar energy" return fresh content with
   no `cached` field at all. The absence of a field has to mean "fresh", which is a weak
   contract.
4. **`generated_at` is non-deterministic.** Three back-to-back `/research?topic=solar+energy`
   calls returned byte-identical `summary` text but three different timestamps.
5. **Diacritics stripped server-side.** Asking for `São Paulo` echoes back `"Sao Paulo"`.
6. **Asymmetric validation errors.** Missing `?location=` returns `422`; empty `?location=`
   returns `404`. For `/research`, missing returns `422` but empty topic returns `200`
   with a stale cache. Same shape of error, different status codes depending on whether
   the param is omitted or empty.
7. **Auth timing side-channel.** No-key 401 takes ~6 seconds; wrong-key 401 takes ~360ms.
   Identical response bodies.
8. **Case-insensitive `X-API-Key` header.** Lowercase works. Minor, but worth knowing for
   any client that lowercases headers (HTTP/2 normalises them).

---

## How I figured out what was happening

### Step 1 — Write a probe script, not a curl-by-curl

`scripts/probe_api.py`. It hits each endpoint with a matrix of inputs:

- Happy path
- Missing parameter
- Empty string parameter
- Unicode input
- Very long input
- Whitespace-only input
- Unknown extra parameters
- Same input repeated 3× (for determinism)
- Parallel concurrent calls (for rate-limit behaviour)
- Auth variants (no key, wrong key, lowercase header)

For each request it logs the status code, content-type, response time, and full body.
Output went to `probe-output.md`.

### Step 2 — The first probe was largely useless, and that was the discovery

When I ran it, almost every `/research` body came back as `{"status":"throttled", ...}` — including the
"happy path" call. My first reaction was *"the API is broken"*. My second reaction, after
looking at the response code, was *"the API returns 200 OK on rate limit, that's why I'm
seeing this for everything."* That was the single most important discovery moment —
everything else flowed from realising that throttle is communicated in-band, not via the
status code.

### Step 3 — Spaced re-probe to actually see the responses

I wrote `scripts/_reprobe_targeted.py` that puts a 12-second gap between requests. Output
went to `reprobe-output.md`. With the throttle finally out of the way I could see:

- The two different weather shapes (London came back flat once, then array on the next run).
- The stale-cache fields on `/research` for empty and unicode topics.
- The non-deterministic `generated_at` timestamps across identical "solar energy" calls.

### Step 4 — Run identical calls in a row

A lot of the quirks only show up under repetition. The schema variation on `/weather` and
the `generated_at` drift are both invisible if you only do one happy-path call per location.
Three back-to-back calls of the same thing was the cheapest way to surface them.

### Step 5 — Pay attention to timing

The 17× gap between no-key (6s) and wrong-key (360ms) 401 responses jumped out only
because I had elapsed time next to each line. If I'd been reading just bodies, I'd never
have noticed.

---

## How I reasoned about handling each one

**Guiding rule:** normalise at the *tool layer*, not the HTTP client. The HTTP client
(`tools/http.py`) handles transport-level concerns — real `429`s with `Retry-After`,
`5xx`s, connection errors, timeouts, retry-with-backoff. Content-shape weirdness —
throttle bodies, schema variation, staleness — is a tool concern, because the right
response depends on what the LLM and user need, not the wire protocol. Keeping the
HTTP client provider-agnostic also means it's reusable for any future tool.

Per-quirk reasoning:

- **Soft throttle (F-01).** I considered transparently retrying inside the HTTP client.
  Decided against it: the throttle window can be ~30s, and silently waiting that long in a
  chat is worse UX than telling the user. So the tool returns a structured error with
  `retry_after_seconds` and the model relays it. The LLM gets to decide whether to wait or
  ask the user how to proceed.
- **Schema variation (F-02).** I promote the first entry of `conditions[]` to the top
  level and add `multiple_conditions: true` plus the secondary entries. The LLM sees a
  stable schema but can still mention the other forecasts if it wants. Picking "first" is
  arbitrary but at least it's consistent.
- **Staleness (F-07).** When `cached: true`, I attach a `staleness_warning` field with
  the age in days. The LLM has the info to caveat its response. I deliberately don't drop
  stale results — partial info is usually better than none, and the user might still want it.
- **Non-deterministic `generated_at` (F-08).** I strip it. It's noise that breaks any cache
  or replay-based test, and the content underneath is deterministic.
- **Empty params (F-04).** I guard at the tool boundary (`if not location: return error`)
  rather than trusting the server's 404. Saves a round-trip and makes the contract clearer
  in code.
- **Diacritics (F-03).** Attach `location_query` with the original requested name to the
  result so the model can refer back to it if the user asks "what about São Paulo?" and the
  response says "Sao Paulo".
- **Timing channel (F-05), case-insensitive header (F-06).** Documented, no code change.
  Not my API to fix, and our client already uses the canonical casing and always sends a key.

---

## What surprised me

- **HTTP 200 for throttle.** This was the biggest surprise. It violates a pretty universal
  HTTP convention and would silently break a less paranoid client. It's also the easiest
  quirk to write off as "weird, but I got 200 so I guess it worked" — exactly the kind of
  thing that shows up as a model hallucination in production.
- **The stale cache returning 2024 content in 2026.** It's indistinguishable from a real
  response unless you specifically check for `cached`. A user asking about a niche topic
  could get year-old data presented as current.
- **The schema variation on `/weather`.** I'd assumed the API would at least be
  self-consistent per location. Same-location-different-shape forced me to write the
  normaliser to handle both shapes rather than detecting the right one upfront.
- **The 6-second wait on missing auth.** Almost certainly an artificial sleep on the
  server side. From a client perspective, the failure mode for "user forgot to set
  `ELYOS_API_KEY`" is a 6-second hang before a clear error. I noted it but didn't paper
  over it.
- **`generated_at` drift on identical content.** Three calls returning byte-identical
  summaries but three different timestamps suggests the timestamp is set at response-build
  time, not content-generation time. Looks deliberate, possibly to discourage caching.

---

## What I'm less sure about and would investigate further

The assignment prompt explicitly says it's fine to say *"I'm not sure about X, but here's
how I'd find out"*. Here are mine:

- **Other undocumented response shapes on `/weather`.** I observed two — flat and array.
  If a third exists (say, an error sub-shape with status `200`), my normaliser passes it
  through unchanged and the LLM might mis-parse it. *How I'd find out:* add a sentinel
  assertion in the normaliser that fires if the response is missing all expected top-level
  keys, and log to a "schema-drift" stream that I'd review periodically.

- **The exact rate-limit window.** I see `retry_after_seconds` values in the 22–27 range,
  but I don't know if that's a fixed bucket or a sliding window. *How I'd find out:* hit
  the endpoint at slowly-increasing intervals (5s, 10s, 15s, …) and find the breakpoint
  where throttling stops. I didn't do this because the assignment doesn't need it, but in
  production I'd want to know.

- **Whether `cached: true` ever appears with fresh content.** Right now I treat
  `cached: true` as a binary "stale" signal. If the API ever returns `cached: true` with a
  small `cache_age_seconds` (e.g., 60s), my warning is scary for no reason. *How I'd find
  out:* probe a wider range of topics, including ones I'd expect to be borderline (recent
  news topics, slightly misspelled common words) and look at the `cache_age_seconds`
  distribution.

- **What `data: null` actually means outside throttle.** I've only seen it inside the
  throttle body. If it appears in other contexts (server-side error, malformed input that
  passes validation), my code would still surface "throttled" as the error reason, which
  would be misleading. *How I'd find out:* fuzz with weirder inputs — control characters,
  zero-width Unicode, structurally valid but semantically nonsense topics.

- **Whether the API is idempotent under concurrency.** I ran 5 parallel `/research` calls
  and they all returned 105-byte bodies (almost certainly all throttled). I didn't get
  clean concurrent reads. *How I'd find out:* warm up with a single call, then fire N
  parallel requests with unique topics, check that each gets a coherent response and that
  none cross-contaminates another's body.

- **What I didn't fuzz hard enough.** I tried Unicode, long input, empty, whitespace, and
  a handful of malformed combos. I didn't try control characters, very large payloads,
  SQL/template-injection-shaped strings, or unusual content-types on the request. Not
  because they don't matter, but because the assignment is about a chat client, not a
  pentest. If this were going to production I'd push further.

- **Whether the probe results are stable over time.** I ran the probe once on 2026-05-14.
  These quirks could change without me noticing. *How I'd find out:* run the probe on CI
  nightly, diff the output against a checked-in baseline, alert on schema changes. I'd
  also keep an eye on `generated_at` shifting backwards (a sign the cache layer was reset)
  and on the throttle threshold drifting.

---

## A known bug, and how I'd fix it (rather than hide it)

While testing the chat UI I noticed that pressing **Esc during a streaming response
didn't cancel** — even though the placeholder explicitly said "[streaming — press Esc to
cancel]".

**Root cause:** the handler was on the `<Textarea>` element's `onKeyDown`, but the textarea
is `disabled={streaming}` during a response, and disabled form elements don't fire
keyboard events. So the affordance was advertised but unreachable.

**Fix:** registered a `window`-level keydown listener while streaming is active. Code is
in `web-ui/src/components/Composer.tsx` (the `useEffect` that adds and removes the
listener on the `streaming` boundary).

I'm mentioning this because the failure mode is interesting: the cancellation pipeline
all the way down to the backend works perfectly — the `CancelToken`, the polling in the
provider stream, the polling in the HTTP retry loop. It just wasn't being triggered from
the UI. Easy to miss, because every layer of the stack passes its unit tests.

It also matches the assignment's framing exactly — *"showing a bug and explaining how
you'd fix it is better than hiding it"*. The bug existed, I found it during demo prep,
I fixed the root cause (focus / event-target mismatch on a disabled element) rather than
working around it (e.g., not disabling the textarea), and I documented why the original
approach was unreachable.

---

## Cross-reference

- Full technical breakdown of every quirk with severity, repro steps, observed vs.
  expected, impact, and handler location: [`api-findings.md`](api-findings.md).
- Probe scripts: [`scripts/probe_api.py`](../scripts/probe_api.py), reprobe variant at `scripts/_reprobe_targeted.py`.
- Probe outputs: [`probe-output.md`](../probe-output.md), [`reprobe-output.md`](../reprobe-output.md).
- Normaliser implementations: `src/elyos_chat/tools/weather.py::_normalise`,
  `src/elyos_chat/tools/research.py::_normalise`.
