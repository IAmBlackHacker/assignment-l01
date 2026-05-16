# Code Walkthrough

How streaming works and how cancellation works are the two design questions worth
explaining in detail. Everything else is supporting context.

## Architecture overview

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

## Streaming

The data path, end to end:

1. **Provider yields events.** In `providers/anthropic.py:41`, an
   `async with client.messages.stream(...) as stream:` iterates the SDK's event stream.
   Each `TextDelta` event yields a `("text", chunk)` event. Tool-use events yield
   `("tool_start", ToolCall)` and `("tool_end", ToolResult)` in the same loop.
2. **Renderer enqueues.** In `web/ws_text.py:104`, `WSRenderer.write(text)` puts
   `{"type": "text_delta", "text": chunk}` onto an `asyncio.Queue`. Tool events go onto
   the same queue via `begin_tool()` and `end_tool()` so ordering is preserved.
3. **Drainer pumps to the websocket.** A separate task pulls from the queue and
   `await ws.send_json(...)`s to the browser. Two tasks — producer (the chat session
   running the provider stream) and consumer (the drainer) — coordinate via the queue.
4. **Frontend store applies events.** In `web-ui/src/state/store.ts:105`, the store
   handler for `text_delta` appends `chunk` to the current assistant message and sets
   `streaming: true`.
5. **React re-renders.** `MessageList.tsx:81` displays the assistant message; the
   `streaming` flag triggers a CSS cursor pulse at the end of the message until the
   final event.

Why a queue between the stream loop and the websocket send? Two reasons:

- It decouples producer rate from consumer rate. If the LLM bursts 50 deltas while the
  network is slow, the deltas buffer in memory rather than backpressure-ing the SDK
  stream.
- It lets tool events interleave correctly with text events. Both go through the same
  ordered queue, so the frontend sees `text → text → tool_start → tool_result → text`
  exactly as it happened, with no special cross-stream synchronisation logic.

There's no buffering or batching of text deltas. The browser sees a websocket frame per
token, and the cursor pulse on `MessageList.tsx:81` makes the streaming visible. Latency
from "Anthropic emits token" to "browser renders token" is bounded by the websocket
round-trip, not by any chunking inside our code.

---

## Cancellation

Cancellation is **cooperative**, not preemptive. That's the most important design
decision in the codebase.

The components:

- **`CancelToken`** — `src/elyos_chat/chat/cancel.py:7`. Wraps an `asyncio.Event`. Two
  methods: `cancel()` sets the event, `cancelled()` returns whether it's set. There's
  also a coroutine `wait_until_cancelled_or(seconds)` that returns `True` if the event
  was set before the timeout (used by the HTTP retry backoff).
- **Per-turn ownership.** `ChatSession.handle_user_input()` creates a fresh `CancelToken`
  at the start of every turn. The token is stored as `self._active_cancel`. When the
  turn finishes (or cancels), the token is cleared.
- **`cancel_current()`** — `session.py:45`. Sets the active token's event. Idempotent —
  safe to call when nothing is active.

Where the token is polled:

- **Provider stream loop** — `providers/anthropic.py:45`. On every event in the SDK's
  streaming iterator, we check `if cancel.cancelled(): break`. The OpenAI and Gemini
  providers do the same in their respective loops.
- **HTTP retry loop** — `tools/http.py:71` and `:118`. Before each retry attempt and
  during the exponential backoff wait, we check the token. The backoff wait specifically
  uses `asyncio.wait_for(cancel_event.wait(), timeout=backoff_seconds)` so a cancel
  mid-wait unblocks immediately rather than sleeping out the full backoff.
- **Tool dispatcher** — `session.py:110`. Before dispatching the next tool call, we
  check the token. Tools currently in flight finish their HTTP call (or get cancelled
  by the HTTP-layer polling) and the dispatcher then exits cleanly.

The trigger path, frontend to backend:

1. User presses **Esc**. The `useEffect` in `web-ui/src/components/Composer.tsx`
   registers a `window`-level keydown listener while streaming is active, and on Esc
   calls `textWs.cancel()`. (The earlier version of this listener was on the textarea's
   `onKeyDown`, but the textarea is `disabled` during streaming so the listener never
   fired — see [`api-discovery.md`](api-discovery.md) for the bug walkthrough.)
2. `textWs.cancel()` sends `{"type": "cancel"}` over the websocket.
3. `web/ws_text.py:189` receives the message and calls `session.cancel_current()`.
4. The cancel event flips. Next poll in any layer — provider stream, HTTP retry, tool
   dispatcher — sees `cancelled() == True` and returns / breaks.
5. The chat session loop exits, the websocket sends a final `{type: "turn_cancelled"}`
   event, the frontend store flips `streaming: false`, and the UI returns to the input
   state.

**Test coverage:** `tests/test_cancel.py` verifies mid-stream cancellation stops
iteration; `tests/test_cancel_token.py` covers the token's basic state transitions.

---

## Other modules, briefly

- **History serialisation** — `chat/history.py` writes one JSONL line per turn. Resume
  reads lines back into memory. Simple, greppable, no schema migrations. The lack of
  schema versioning is the weakest part — see [`self-critique.md`](self-critique.md).
- **Tool registry** — `tools/registry.py` translates a canonical tool schema into each
  provider's tool format (Anthropic's `tools=[...]`, OpenAI's `tools=[...]` with a
  different field layout, Gemini's `function_declarations`). One source of truth, three
  encoders.
- **Voice mode** — `web/ws_voice.py` is an OpenAI Realtime relay used by the voice
  toggle in the top bar. Out of scope for the assignment but functional. It bypasses the
  text `CancelToken` and uses Realtime's own VAD/barge-in for cancellation, which is one
  of the things I'd consolidate with more time.
