# Demo (3–4 min)

Three beats: a weather query, a research query with pending state, and a cancel mid-flight.
Goal is to show the *experience* working end-to-end, not every feature.

## Beat 1 — Weather (≈30s)

Type: **"What's the weather in London?"**

What to point out as it plays:
- Streamed answer (cursor pulse on the assistant message while text deltas arrive).
- Tool spinner appears for `weather` before the model speaks — proves tools are called, not hallucinated.
- The result row shows the city, the temperature, and (if the API returned the array shape) a "multiple conditions" note.

If the array shape comes back, mention briefly: *"the API sometimes returns multiple conditions for the same city — the tool normalises that so the model sees a stable schema."* This sets up the API Discovery section without spending demo time on it.

## Beat 2 — Research with pending state (≈60s)

Type: **"Research solar energy briefly."**

What to point out:
- The `research` tool row appears immediately with a spinner and a **live elapsed-time counter**.
- The counter ticks up past 2–3 seconds — long enough that the user knows the system is working, not stuck.
- When the tool returns, the row collapses to a result and the streamed assistant answer begins.

Optional aside if there's time: *"the elapsed time comes from a `tool_use_start` event the backend emits when the tool begins, and a `tool_result` event when it finishes — the frontend just renders the gap."*

## Beat 3 — Cancel mid-flight (≈60s)

Type: **"Research the history of trans-pacific shipping in detail."** (Any long-ish research prompt.)

While the spinner is running:
- Press **Esc**.
- The Square button reverts to Send, the spinner disappears, the assistant message is left as-is or marked cancelled.

What to say while doing this:
- *"Cancellation is cooperative. The Esc keypress sends `{type: 'cancel'}` over the websocket, the server sets an `asyncio.Event`, and every layer — the LLM stream, the HTTP retry loop, the tool dispatcher — polls that event between operations. The HTTP request to the Elyos API is interrupted at the next backoff boundary, not yanked mid-write."*

If you have a terminal tail of the backend logs visible, flick to it briefly so the audience sees the cancel propagating. It's worth a few extra seconds because it's the strongest visual evidence that cancellation is wired all the way down.

After cancel, send one more short message (e.g., "thanks") to demonstrate history is preserved and the next turn works normally.

## Pre-demo checklist

1. `./scripts/run_web.sh` running. FastAPI on `:8000`, Vite on `:5173`. Open `http://localhost:5173`.
2. **Pre-warm:** run one weather query and one research query *before* recording — cold-start of uvicorn/Vite adds a second or two to the first call.
3. Verify Esc-cancel works after the fix (see `code-walkthrough.md` — the handler is now `window`-level because the textarea is `disabled` during streaming).
4. Backend log tail in a visible terminal: `tail -f` whatever uvicorn is writing to, or just keep the `run_web.sh` terminal in view.
5. `.env` has `ELYOS_API_KEY` and the matching provider key set. If you forget the Elyos key, the first call hangs for ~6s (see F-05 in `api-findings.md`).

## Fallbacks if something breaks

- **Tool call fails / API throttled.** Calmly say *"the API soft-throttles via HTTP 200 with a throttle body — I detect that and surface it; let me try again in a moment."* This actually demonstrates graceful API handling rather than hiding it.
- **Streaming feels too fast to see.** Pick a longer prompt ("explain in detail") so the cursor pulse is visible for a few seconds.
- **Esc cancel looks instant.** Pick a deeper research prompt so the cancel happens visibly mid-tool-call.

## What NOT to demo

Skip these unless explicitly asked — they eat time:

- Voice mode. It works but it's a 2-minute setup explanation (mic permissions, Realtime API) and not in the assignment requirements.
- Provider switching (Anthropic / OpenAI / Gemini). Cool but tangential.
- Session resume from the sidebar. Save for the code-walkthrough section if you go there.

Stick to the three beats. Better to nail them than rush through six.
