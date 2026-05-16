# Code Walkthrough (3–4 min)

Focus on the two things the prompt asks about: **how streaming works** and **how
cancellation works**. Everything else is supporting context.

## 30-second architecture overview

Three layers, plus a thin web shim:

```
src/elyos_chat/
  providers/    LLM SDK adapters (anthropic.py, openai.py, gemini.py) — Provider Protocol
  tools/        Elyos API client (http.py) + tool handlers (weather.py, research.py) + registry
  chat/         ChatSession orchestrator, History (JSONL), CancelToken, Events
web/            FastAPI app: ws_text.py (chat), ws_voice.py (Realtime relay), sessions.py
web-ui/src/     React + Zustand store + WS client
```

The chat session owns the orchestration loop and the cancel token. Providers stream from
the LLM. Tools call the Elyos API. The web layer is a thin renderer that pumps events
between the session and the websocket.

---

## Streaming (~90s of talk)

The data path, end to end:

1. **Provider yields events.** In `providers/anthropic.py:41`, an
   `async with client.messages.stream(...) as stream:` iterates the SDK's event stream.
   Each `TextDelta` event yields a `("text", chunk)` event. Tool-use events yield
   `("tool_start", ToolCall)` and `("tool_end", ToolResult)` in the same loop.
2. **Renderer enqueues.** In `web/ws_text.py:104`, `WSRenderer.write(text)` puts
   `{"type": "text_delta", "text": chunk}` onto an `asyncio.Queue`. Tool events go onto
   the same queue via `begin_tool()` and `end_tool()` so ordering is preserved.
3. **Drainer pumps to the websocket.** A separate task pulls from the queue and `await ws.send_json(...)`s
   to the browser. Two tasks — producer (the chat session running the provider stream)
   and consumer (the drainer) — coordinate via the queue.
4. **Frontend store applies events.** In `web-ui/src/state/store.ts:105`, the store
   handler for `text_delta` appends `chunk` to the current assistant message and sets
   `streaming: true`.
5. **React re-renders.** `MessageList.tsx:81` displays the assistant message; the `streaming`
   flag triggers a CSS cursor pulse at the end of the message until the final event.

**Why a queue between the stream loop and the websocket send?** Two reasons:

- It decouples producer rate from consumer rate. If the LLM bursts 50 deltas while the
  network is slow, the deltas buffer in memory rather than backpressure'ing the SDK stream.
- It lets tool events interleave correctly with text events. Both go through the same
  ordered queue, so the frontend sees `text → text → tool_start → tool_result → text`
  exactly as it happened, with no special cross-stream synchronisation logic.

**The key thing to call out if asked:** there's no buffering or batching of text deltas.
The browser sees a websocket frame per token, and the cursor pulse on `MessageList.tsx:81`
makes the streaming visible. Latency from "Anthropic emits token" to "browser renders
token" is bounded by the websocket round-trip, not by any chunking inside our code.

---

## Cancellation (~90s of talk)

Cancellation is **cooperative**, not preemptive. That's the most important design decision
in the whole codebase.

The components:

- **`CancelToken`** — `src/elyos_chat/chat/cancel.py:7`. Wraps an `asyncio.Event`. Two
  methods: `cancel()` sets the event, `cancelled()` returns whether it's set. There's also
  a coroutine `wait_until_cancelled_or(seconds)` that returns `True` if the event was set
  before the timeout (used by the HTTP retry backoff).
- **Per-turn ownership.** `ChatSession.handle_user_input()` creates a fresh `CancelToken`
  at the start of every turn. The token is stored as `self._active_cancel`. When the turn
  finishes (or cancels), the token is cleared.
- **`cancel_current()`** — `session.py:45`. Sets the active token's event. Idempotent —
  safe to call when nothing is active.

Where the token is polled:

- **Provider stream loop** — `providers/anthropic.py:45`. Every event in the SDK's
  streaming iterator, we check `if cancel.cancelled(): break`. The OpenAI and Gemini
  providers do the same in their respective loops.
- **HTTP retry loop** — `tools/http.py:71` and `:118`. Before each retry attempt and during
  the exponential backoff wait, we check the token. The backoff wait specifically uses
  `asyncio.wait_for(cancel_event.wait(), timeout=backoff_seconds)` so a cancel mid-wait
  unblocks immediately rather than sleeping out the full backoff.
- **Tool dispatcher** — `session.py:110`. Before dispatching the next tool call, we check
  the token. Tools currently in flight finish their HTTP call (or get cancelled by the
  HTTP-layer polling) and the dispatcher then exits cleanly.

The trigger path, frontend to backend:

1. User presses **Esc**. The `useEffect` in `Composer.tsx` (added during the bug fix —
   see `api-discovery.md` for context) calls `textWs.cancel()`.
2. `textWs.cancel()` sends `{"type": "cancel"}` over the websocket.
3. `web/ws_text.py:189` receives the message and calls `session.cancel_current()`.
4. The cancel event flips. Next poll in any layer — provider stream, HTTP retry, tool
   dispatcher — sees `cancelled() == True` and returns / breaks.
5. The chat session loop exits, the websocket sends a final `{type: "turn_cancelled"}`
   event, the frontend store flips `streaming: false`, and the UI returns to the input
   state.

**Test coverage:** `tests/test_cancel.py` and `tests/test_cancel_token.py`. The first
verifies mid-stream cancellation stops iteration; the second covers the token's basic
state transitions.

---

## What to skip unless asked

- **History serialisation.** `chat/history.py` writes one JSONL line per turn. Simple and
  works, but not interesting in a 4-minute walkthrough. Mention it only if asked about
  resume / persistence.
- **Tool registry.** `tools/registry.py` translates a canonical tool schema into each
  provider's tool format. Cute, but a tangent.
- **Voice mode.** `ws_voice.py` and the OpenAI Realtime relay are out of scope for the
  assignment.

## Talking-point flow if asked "walk me through it"

1. *"Three layers — providers, tools, chat session. Web is a thin renderer."* (15s)
2. *"Streaming — provider yields events, renderer enqueues onto a shared queue, drainer
   pumps to the websocket, store accumulates, React shows a cursor pulse."* (90s)
3. *"Cancellation — cooperative token, polled in every long-running loop. Trigger goes
   UI → websocket → session → token. Why cooperative? So cleanup is predictable —
   stream loops, HTTP retries, history writes, none can be interrupted mid-write."* (90s)
4. *"Tests cover both. `test_cancel.py` proves mid-stream cancel stops iteration."* (15s)

That's the whole walkthrough. Resist the urge to dive into providers, tool registry, or
voice mode unless explicitly asked — it'll eat the clock.
