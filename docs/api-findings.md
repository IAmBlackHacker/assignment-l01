# Elyos API findings

Base URL: `https://elyos-interview-907656039105.europe-west2.run.app`
Probe script: `scripts/probe_api.py`
Probed on: 2026-05-14

The Elyos tool API exposes two endpoints — `/weather` and `/research` — that each contain several
non-obvious behavioral quirks. These quirks were discovered by running `scripts/probe_api.py`
(initial run) and `scripts/_reprobe_targeted.py` (spaced re-run, 12 s between requests to avoid
rate limiting). The findings below document each quirk with exact reproduction steps, observed
behaviour, naive expectation, downstream impact if unhandled, and the normalisation function that
addresses it.

## Summary

| ID | Endpoint | Quirk | Severity | Handler |
|---|---|---|---|---|
| F-01 | both | Soft throttling via HTTP 200 with `status=throttled` | high | `tools/weather.py::_normalise`, `tools/research.py::_normalise` |
| F-02 | /weather | Response shape is non-deterministic: flat object vs. `conditions` array | high | `tools/weather.py::_normalise` |
| F-03 | /weather | Unicode diacritics stripped server-side (São Paulo → Sao Paulo) | low | `tools/weather.py::_normalise` |
| F-04 | both | Asymmetric error codes: empty string → 404, missing param → 422 | medium | `tools/weather.py::_normalise`, `tools/research.py::_normalise` |
| F-05 | /weather | No-key auth ~17× slower than wrong-key (timing side-channel) | low | documentation only |
| F-06 | /weather | Header name is case-insensitive (`x-api-key` accepted) | low | documentation only |
| F-07 | /research | Stale-cache responses for obscure/empty topics — signalled via `"cached":true` | medium | `tools/research.py::_normalise` |
| F-08 | /research | `generated_at` timestamp is non-deterministic even for identical summaries | low | `tools/research.py::_normalise` |

---

### F-01: Soft throttling via HTTP 200 with `status=throttled`

- **Severity:** high
- **Repro:**
  ```bash
  # Fire several rapid requests without spacing
  for i in 1 2 3 4 5 6 7 8; do
    curl -s -H "X-API-Key: $ELYOS_API_KEY" \
      "$ELYOS_API_BASE/weather?location=London"
  done
  ```
- **Observed:** HTTP 200, body:
  ```json
  {"status":"throttled","message":"Rate limit exceeded. Please wait.","retry_after_seconds":27,"data":null}
  ```
- **Expected:** HTTP 429 with a `Retry-After` header, which the HTTP client's retry logic already
  handles (`TRANSIENT_STATUSES = {429, …}`).
- **Impact:** Because the status code is 200, `ToolHttpClient.get()` treats the response as
  success and passes the throttle body directly to the LLM. The LLM receives `{"data": null}` with
  no weather or research content and may hallucinate or produce confusing output.
- **Handler:** `tools/weather.py::_normalise` and `tools/research.py::_normalise` — detects
  `body["status"] == "throttled"` and returns a structured error dict with `retry_after_seconds`
  so the model can relay the rate-limit message to the user.

---

### F-02: Non-deterministic weather response shape (flat vs. conditions array)

- **Severity:** high
- **Repro:**
  ```bash
  # Same location — different calls may return different shapes
  curl -H "X-API-Key: $ELYOS_API_KEY" "$ELYOS_API_BASE/weather?location=London"
  curl -H "X-API-Key: $ELYOS_API_KEY" "$ELYOS_API_BASE/weather?location=Tokyo"
  ```
- **Observed:** Two documented shapes:
  - Flat: `{"location":"London","temperature_c":10.4,"condition":"Moderate rain","humidity":66}`
  - Array: `{"location":"Tokyo","conditions":[{"temperature_c":18.3,"condition":"Partly cloudy","humidity":77},{"temperature_c":17.3,"condition":"light rain","humidity":90}],"note":"Multiple conditions reported"}`
  
  London itself returned the flat shape in one probe run and the array shape in another, confirming
  the variation is per-call rather than per-location.
- **Expected:** A consistent response schema with a single top-level `temperature_c`, `condition`,
  and `humidity`.
- **Impact:** If the LLM receives the array shape unprepared, it must handle a `conditions` list
  when it expects scalar fields. Tool schemas or downstream renderers written for the flat shape
  will silently miss the secondary conditions or raise KeyErrors.
- **Handler:** `tools/weather.py::_normalise` — when `conditions` is a list, promotes the first
  entry to the top level as `primary_condition` and sets `multiple_conditions: bool`.

---

### F-03: Unicode diacritics stripped server-side

- **Severity:** low
- **Repro:**
  ```bash
  curl -H "X-API-Key: $ELYOS_API_KEY" \
    "$ELYOS_API_BASE/weather?location=S%C3%A3o%20Paulo"
  ```
- **Observed:** HTTP 200, body:
  ```json
  {"location":"Sao Paulo","temperature_c":12.1,"condition":"Mist","humidity":94}
  ```
  The `location` field in the response is `"Sao Paulo"`, not `"São Paulo"`.
- **Expected:** The response `location` field to echo back the submitted name, or at least include
  the original alongside the normalised form.
- **Impact:** The model or UI may display `"Sao Paulo"` to a user who asked about `"São Paulo"`,
  which looks like a typo. Downstream string matching on city name will fail if the caller stores
  the original query string.
- **Handler:** `tools/weather.py::_normalise` — attaches `"location_query"` with the original
  requested name so the model can refer back to it.

---

### F-04: Asymmetric error codes for empty vs. missing parameter

- **Severity:** medium
- **Repro:**
  ```bash
  # Missing param → 422
  curl -H "X-API-Key: $ELYOS_API_KEY" "$ELYOS_API_BASE/weather"

  # Empty string → 404
  curl -H "X-API-Key: $ELYOS_API_KEY" "$ELYOS_API_BASE/weather?location="
  ```
- **Observed:**
  - Missing: HTTP 422, `{"detail":[{"type":"missing","loc":["query","location"],"msg":"Field required","input":null}]}`
  - Empty: HTTP 404, `{"error":"Location \"\" not found"}`
- **Expected:** Both cases to return 422 (validation error) since an empty string is semantically
  equivalent to a missing value.
- **Impact:** Code that only handles 422 for "bad input" will silently treat 404-for-empty-param
  differently from 422-for-missing-param. The `ToolHttpClient` maps both to `Result.err`, but the
  error message will differ. Callers must not assume HTTP 404 always means "location does not
  exist"; it can also mean the parameter was empty.
- **Handler:** `tools/weather.py::_normalise` and `tools/research.py::_normalise` — the handlers
  already guard `if not location` / `if not topic` before calling the HTTP layer, preventing the
  empty-string case from ever reaching the API. The finding is documented for completeness and
  to ensure the guard is retained.

---

### F-05: No-key auth is ~17× slower than wrong-key auth (timing side-channel)

- **Severity:** low
- **Repro:**
  ```bash
  # No key — measure time
  time curl "$ELYOS_API_BASE/weather?location=London"

  # Wrong key — measure time
  time curl -H "X-API-Key: wrong" "$ELYOS_API_BASE/weather?location=London"
  ```
- **Observed:**
  - No key: HTTP 401 in **6064ms**
  - Wrong key: HTTP 401 in **358ms**
  - Both return identical body: `{"error":"Invalid or missing API key"}`
- **Expected:** Both paths to return 401 in roughly equal time (fast fail).
- **Impact:** A timing side-channel could allow an attacker to distinguish "no key provided" from
  "wrong key provided" despite the identical 401 body. Not directly exploitable by our application,
  but worth noting for the API operator. For our client, the 6-second delay on missing key means a
  user who forgets to set `ELYOS_API_KEY` will experience a long hang before getting an error.
- **Handler:** documentation only — `ToolHttpClient` already sends the key on every request.

---

### F-06: `X-API-Key` header accepted case-insensitively

- **Severity:** low
- **Repro:**
  ```bash
  # Lowercase variant
  curl -H "x-api-key: $ELYOS_API_KEY" "$ELYOS_API_BASE/weather?location=London"
  ```
- **Observed:** HTTP 200 — request succeeds with lowercase `x-api-key`.
- **Expected:** Some APIs are strict about header casing; the documented header name is
  `X-API-Key`.
- **Impact:** Positive finding — our client uses the canonical casing `X-API-Key` (correct), and
  the server's case-insensitivity ensures compatibility with HTTP/1.1 and HTTP/2 proxies that
  normalise header names to lowercase. No action needed, but confirms no header-case bug exists.
- **Handler:** documentation only.

---

### F-07: Stale-cache responses for obscure or empty topics

- **Severity:** medium
- **Repro:**
  ```bash
  # Empty topic
  curl -H "X-API-Key: $ELYOS_API_KEY" "$ELYOS_API_BASE/research?topic="

  # Obscure topic
  curl -H "X-API-Key: $ELYOS_API_KEY" "$ELYOS_API_BASE/research?topic=caf%C3%A9+science"
  ```
- **Observed:** HTTP 200, body includes extra fields:
  ```json
  {
    "topic": "café science",
    "summary": "Research on 'café science' from early 2024. This cached summary may not reflect recent developments.",
    "sources": ["nature.com","sciencedirect.com","arxiv.org"],
    "generated_at": "2024-03-15T09:00:00Z",
    "cached": true,
    "cache_age_seconds": 26784000
  }
  ```
  Fresh requests for well-known topics (e.g. `"solar energy"`) do NOT include `"cached"` or
  `"cache_age_seconds"`, and have a current `generated_at`.
- **Expected:** Either a consistent schema with `cached` always present (defaulting to `false`),
  or a clearly different status for stale content.
- **Impact:** The model receives data that may be ~10 months old (26784000 s ≈ 310 days) with no
  automatic warning. If `_normalise` does not surface the staleness, the LLM may present outdated
  information as current research.
- **Handler:** `tools/research.py::_normalise` — when `body.get("cached") is True`, appends a
  `"staleness_warning"` to the returned dict so the model can caveat its response.

---

### F-08: `generated_at` timestamp is non-deterministic across identical requests

- **Severity:** low
- **Repro:**
  ```bash
  curl -H "X-API-Key: $ELYOS_API_KEY" "$ELYOS_API_BASE/research?topic=solar+energy"
  curl -H "X-API-Key: $ELYOS_API_KEY" "$ELYOS_API_BASE/research?topic=solar+energy"
  curl -H "X-API-Key: $ELYOS_API_KEY" "$ELYOS_API_BASE/research?topic=solar+energy"
  ```
- **Observed:** All three calls return the same `summary` text byte-for-byte, but `generated_at`
  differs per call:
  - `"2026-05-14T10:26:54.821307+00:00"`
  - `"2026-05-14T10:27:10.924514+00:00"`
  - `"2026-05-14T10:27:31.122728+00:00"`
- **Expected:** Either a stable `generated_at` (content hash-based) or true per-call generation
  that produces different summaries.
- **Impact:** The summary is deterministic, but `generated_at` changes on every call. Any
  deduplication, caching, or idempotency check that uses `generated_at` will incorrectly treat
  identical responses as distinct. Clients should not treat `generated_at` as a stable content
  identifier.
- **Handler:** `tools/research.py::_normalise` — strips `generated_at` from the returned dict
  (or renames it to `timestamp`) so the model's tool result is stable and does not confuse
  caches or diff-based logging.
