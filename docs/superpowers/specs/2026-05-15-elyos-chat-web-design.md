# Elyos Chat Web UI — Design Spec

**Date:** 2026-05-15
**Author:** Lokesh (kulkarnim@gmail.com)
**Status:** Approved — ready for implementation plan
**Builds on:** [`2026-05-14-elyos-chat-design.md`](2026-05-14-elyos-chat-design.md) (CLI app)

---

## 1. Goal

Add a browser-based UI to the existing elyos-chat CLI app, with:

1. A polished chat experience: sessions sidebar, streaming assistant replies, inline tool-call cards with a pending spinner.
2. Three modes available from the same UI: text chat (streaming), text chat with TTS narration, and full duplex voice mode (talk + listen + interrupt).
3. Reuse of the existing Python core (`ChatSession`, `Provider` adapters, `ToolRegistry`, API quirk handlers F-01..F-08) — no rewrite, no parallel implementation of the tool logic.
4. Persistence shared with the CLI — sessions written by the CLI are visible in the web UI, and vice versa.

The CLI keeps working exactly as it does today; the web UI is additive.

---

## 2. Decisions (from brainstorming)

| Choice | Selection | Rationale |
|---|---|---|
| Backend | Reuse Python + add FastAPI server (`web/server.py`) | Reuses the entire existing core; CLI remains the canonical reference. |
| Transport | Single WebSocket per session per mode | Bidirectional fits voice naturally; one socket = simpler state. |
| Voice infrastructure | OpenAI Realtime API for voice mode | Purpose-built for duplex voice with native VAD, turn-taking, interruption, and tool calling. Smallest path to all three voice features working. |
| Voice scope | STT + TTS + full duplex (barge-in) | User-requested. |
| Frontend stack | Vite + React + TypeScript + Tailwind + shadcn/ui | Fastest dev loop; shadcn primitives are owned-as-code. |
| UI scope | Sessions sidebar + chat main pane + voice/mic/TTS controls in top bar | Demonstrates resume + provider switching cleanly. |
| Text-mode TTS | Browser-native `window.speechSynthesis` | Free, zero-deps, sentence-chunked. |
| Voice-mode TTS | Served by Realtime (assistant audio streamed) | Native to chosen voice infra. |

---

## 3. Architecture — two parallel modes, shared `ToolRegistry`

```
TEXT MODE:
  Browser  ───── WS /ws/text ─────▶  FastAPI  ───▶  ChatSession  ───▶  Provider (Claude/OpenAI/Gemini)
                                          │
                                          └────────▶  ToolRegistry  ───▶  /weather, /research
                                                       (existing F-01..F-08 handlers)

VOICE MODE:
  Browser  ──── PCM16 + JSON ─────▶  FastAPI relay  ─── WS ───▶  OpenAI Realtime
  Browser  ◀─── PCM16 + JSON ────                      ◀────
                                          │
                                          └─ tool_call ─▶  ToolRegistry  ───▶  /weather, /research
                                                            (SAME registry)
```

**Both modes share `ToolRegistry`.** Every API quirk handler from the CLI app (F-01 soft throttle, F-02 multi-condition flatten, F-07 stale-cache warning, …) applies to voice tool calls automatically.

**Both modes share history.** Voice transcripts and text turns append to the same JSONL file under `~/.elyos_chat/sessions/<id>.jsonl`. Sessions show a continuous timeline regardless of mode; turns originating from voice are tagged `voice: true` for UI display.

**Mode separation rule:** the user is in exactly one mode at a time. Switching modes between turns is supported; switching mid-turn is blocked in the UI (voice toggle disabled while `text-streaming`; send disabled while `voice-active`).

---

## 4. File layout

```
elyos-assignment/
├── src/elyos_chat/                  # UNCHANGED — existing CLI app + core
│
├── web/                              # NEW — FastAPI server (Python)
│   ├── __init__.py
│   ├── server.py                    # FastAPI app, lifespan, CORS, static serving
│   ├── ws_text.py                   # /ws/text — text-mode WebSocket handler
│   ├── ws_voice.py                  # /ws/voice — voice-mode relay
│   ├── realtime.py                  # OpenAI Realtime client wrapper
│   ├── sessions.py                  # GET /api/sessions — list JSONL sessions
│   ├── schemas.py                   # pydantic models for WS messages
│   └── deps.py                      # shared registry + http client lifespan
│
├── web-ui/                           # NEW — Vite + React app
│   ├── package.json
│   ├── vite.config.ts                # proxies /ws and /api to :8000
│   ├── tailwind.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── lib/
│       │   ├── ws.ts                # text-mode WebSocket client
│       │   ├── voice.ts             # voice-mode (mic + audio playback + WS)
│       │   ├── audio.ts             # PCM16 ↔ WebAudio helpers (AudioWorklet)
│       │   └── api.ts               # plain HTTP for session list
│       ├── components/
│       │   ├── Sidebar.tsx          # sessions list + "New chat"
│       │   ├── ChatPane.tsx         # message list + streaming
│       │   ├── MessageList.tsx
│       │   ├── ToolRow.tsx          # inline tool card: spinner / ✓ / ✗
│       │   ├── Composer.tsx         # textarea + send + mic button
│       │   ├── VoiceBar.tsx         # voice-mode level meter + status + controls
│       │   ├── TopBar.tsx           # provider, model, TTS toggle, voice toggle
│       │   └── ui/                  # shadcn primitives
│       └── state/
│           └── store.ts             # zustand store
│
├── scripts/
│   └── run_web.sh                   # dev launcher: FastAPI + Vite concurrently
│
├── tests/
│   ├── test_ws_text_protocol.py     # FastAPI TestClient WS protocol tests
│   └── test_ws_voice_relay.py       # voice relay event-translation tests
│
└── docs/superpowers/specs/
    └── 2026-05-15-elyos-chat-web-design.md   # this spec
```

**Dependency direction:** `web/` imports from `elyos_chat.*`; `elyos_chat.*` does not import from `web/`. The CLI is unchanged and remains testable / runnable as before.

**Vite dev:** runs on `:5173`, proxies `/ws/*` and `/api/*` to FastAPI on `:8000`. Production: `vite build` outputs to `web-ui/dist`; FastAPI mounts it as static files.

---

## 5. WebSocket protocol

### 5.1 `/ws/text` — text mode

**Client → Server (JSON only)**

| Type | Fields | Purpose |
|---|---|---|
| `hello` | `session_id`: `"new"` \| `"last"` \| `<id>`; `provider`; `model?`; `system?` | First message on connect. Resolves history. |
| `user` | `content` | Triggers a turn. |
| `cancel` | — | Cancels the in-flight turn. |
| `update_settings` | `provider?`, `model?`, `system?` | Takes effect on next turn. |

**Server → Client (JSON; mirrors `chat/events.py`)**

| Type | Fields | Maps to |
|---|---|---|
| `session_started` | `session_id`, `created`, `resumed_turns?` | First reply to `hello` |
| `user_echo` | `content`, `ts` | Confirms user turn appended |
| `text_delta` | `text` | `TextDelta` |
| `tool_use_start` | `id`, `name` | `ToolUseStart` |
| `tool_use_end` | `id`, `name`, `args` | `ToolUseEnd` |
| `tool_result` | `id`, `name`, `content`, `is_error` | After registry dispatch |
| `turn_end` | `reason` (`stop`/`tool_use`/`cancelled`/`error`) | `TurnEnd` |
| `error` | `message`, `transient` | `Error` |

Translation is mechanical (`to_ws_message(event)` is a single function).

### 5.2 `/ws/voice` — voice mode

**Client → Server**
- Binary frames: PCM16 mono 24 kHz audio chunks.
- JSON control: `hello` (`session_id`, `voice` ∈ `alloy`/`verse`/`shimmer`), `cancel`, `stop`.

**Server → Client**
- Binary frames: PCM16 mono 24 kHz (assistant audio).
- JSON events:
  - `session_started`
  - `speech_started` / `speech_stopped` (VAD signals)
  - `transcript_user_delta`, `transcript_user_done`
  - `transcript_assistant_delta`, `transcript_assistant_done`
  - `tool_use_start`, `tool_use_end`, `tool_result` — **identical shape to text mode**
  - `turn_end`, `error`

**Audio format:** Realtime expects PCM16 mono 24 kHz natively. Browser-side, an `AudioWorkletProcessor` captures raw mic via `getUserMedia` → `AudioContext(sampleRate: 24000)`, slices into 20 ms frames, converts Float32 → Int16 LE, and sends as binary over the WS. Playback path: server binary frames → client Float32 conversion → FIFO `AudioBufferSourceNode` queue.

### 5.3 Tool calls in voice mode

When Realtime emits `response.function_call_arguments.done`, the relay:
1. Emits `tool_use_start` + `tool_use_end` to the client (so the UI shows a spinner + args).
2. Dispatches via the **existing** `ToolRegistry` (same `CancelToken`, same handlers).
3. Emits `tool_result` to the client.
4. Sends a `conversation.item.create` upstream with `type: "function_call_output"` and the JSON-stringified result.
5. Sends `response.create` upstream so the model continues speaking with the result.

Critical: a tool result must always be sent upstream — even on error — or Realtime stalls.

---

## 6. Voice relay flow

Per-connection, two `asyncio.Task`s sharing one `CancelToken`:

1. **`client_pump`** — reads from the browser WS. Binary → push to `upstream_audio_queue`. JSON `cancel` → trigger Realtime's `response.cancel`. JSON `stop` → tear down both tasks.

2. **`upstream_pump`** — reads from the Realtime WS. Switch on event type:
   - `input_audio_buffer.speech_started` → `speech_started` to client
   - `response.audio.delta` → forward binary to client
   - `response.audio_transcript.delta` → `transcript_assistant_delta` + append to in-memory transcript buffer
   - `conversation.item.input_audio_transcription.completed` → `transcript_user_done` + append user turn to JSONL
   - `response.function_call_arguments.done` → tool dispatch flow (§5.3)
   - `response.done` → `turn_end` + append assistant turn to JSONL with `voice: true`
   - `error` → `error` to client

**Backpressure:** bound `upstream_audio_queue` and client `playback_queue` to a few seconds; on overflow, drop oldest frames and emit a `warning` event.

**Lifespan:** relay tasks live for the duration of the WS connection. On disconnect: cancel both pumps, close upstream, flush buffered assistant transcript to JSONL.

---

## 7. Frontend: store + components

### 7.1 Zustand store (`web-ui/src/state/store.ts`)

```typescript
type Mode = "idle" | "text-streaming" | "voice-active";

type Message = {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  toolCalls?: { id: string; name: string; args: object }[];
  toolResults?: { id: string; name: string; content: object; isError: boolean }[];
  voice?: boolean;
  cancelled?: boolean;
  streaming?: boolean;
};

interface Store {
  provider: "anthropic" | "openai" | "gemini";
  model: string | null;
  ttsEnabled: boolean;
  voiceName: "alloy" | "verse" | "shimmer";

  textWs: WebSocket | null;
  voiceWs: WebSocket | null;
  mode: Mode;

  sessionId: string | null;
  messages: Message[];
  sessions: { id: string; title: string; updatedAt: number; messageCount: number }[];
  pendingTools: Record<string, { name: string; startedAt: number }>;

  // actions
  connectText(sessionId: string | "new" | "last"): void;
  sendUserMessage(text: string): void;
  cancelCurrentTurn(): void;
  switchSession(id: string): void;
  startVoiceMode(): Promise<void>;
  stopVoiceMode(): void;
  setProvider(p: string): void;
  setModel(m: string | null): void;
  toggleTts(): void;
  loadSessions(): Promise<void>;
}
```

### 7.2 Component tree

```
<App>
├── <TopBar>       provider dropdown, model input, TTS toggle, voice toggle
├── <main>
│   ├── <Sidebar>          session list, "New chat" button
│   └── <ChatPane>
│       ├── <MessageList>  user bubbles, assistant bubbles (streaming-aware), ToolRow
│       ├── <VoiceBar>     shown only when mode === "voice-active"
│       └── <Composer>     textarea + send + mic button
└── <Toaster>
```

### 7.3 Streaming flow (text mode)

```
User Enter
  → Composer.onSubmit → store.sendUserMessage
    → optimistic user Message; mode = "text-streaming"
    → textWs.send({type: "user", content})
                  ← user_echo (no-op)
                  ← tool_use_start  → pendingTools[id] = {...}
                  ← tool_use_end
                  ← tool_result     → append ToolRow message
                  ← text_delta×N    → append/extend assistant message, streaming: true
                                       (if ttsEnabled, accumulate sentences → speechSynthesis)
                  ← turn_end        → streaming: false; mode = "idle"
```

### 7.4 Visual style

- **Dark mode default**; toggle available.
- **Inter** for chat text; **monospace** for tool args/results.
- **Cyan** for user; **neutral** for assistant; **green/red** for tool ✓/✗.
- **Sidebar fixed 260 px**, collapsible below 640 px viewport.
- **shadcn primitives**: `Button`, `ScrollArea`, `Input`, `Textarea`, `Select`, `Toast`, `Tooltip`.

---

## 8. UI states (ASCII references)

### State A — Idle / browsing history

```
┌──────────────────────────────────────────────────────────────────────────┐
│ elyos chat            [Anthropic ▾] [claude-sonnet-4-6   ] 🔊 TTS  🎙️    │
├──────────────────────┬───────────────────────────────────────────────────┤
│ + New chat           │  you                                              │
│ ▸ Solar energy chat  │  What's the weather in London?                    │
│ ● London weather     │                                                   │
│ ▸ CRISPR research    │  ┌─ ✓ weather ─────────────────────────────────┐  │
│                      │  │ {temp_c: 10.4, condition: "Moderate rain"…} │  │
│                      │  └─────────────────────────────────────────────┘  │
│                      │  assistant                                        │
│                      │  It's 10.4°C in London with moderate rain.        │
│                      ├───────────────────────────────────────────────────┤
│                      │  ┌───────────────────────────────────────┐    ▶   │
│                      │  │ Ask anything…                    🎤   │        │
│                      │  └───────────────────────────────────────┘        │
└──────────────────────┴───────────────────────────────────────────────────┘
```

### State B — Mid-turn (research streaming)

Tool row shows spinning `◐ research … 3.2s elapsed`. Assistant bubble shows blinking cursor `▍` after partial text. Composer disabled, send button becomes stop button (Esc cancels too).

### State C — Voice mode active

Top-bar mic icon shows red dot `🎙️●`. Each turn marked with 🎤 (user spoke) or 🔊 (assistant spoke). Composer replaced by `<VoiceBar>`: live mic-level visualizer (32 bars from `AnalyserNode`), status label (`you're speaking` / `assistant speaking` / `idle`), pause (barge-in), stop (exit voice mode).

---

## 9. Error handling

### 9.1 WebSocket failures

| Failure | Behavior |
|---|---|
| Drop mid-turn (text) | Toast "connection lost — reconnecting"; exponential backoff (250 ms · 2ⁿ, max 5, capped at 10 s); on reconnect, replay `hello` with current `session_id`. Streaming assistant turn marked `cancelled: true` in UI. |
| Server down on first load | Banner "Server not reachable" with retry button. |
| `error {transient: true}` | Toast; keep WS open. |
| `error {transient: false}` | Toast; reset `mode` to idle; re-enable composer. |
| Token gap > 30 s | Subtle "still thinking…" hint. |

### 9.2 Voice failures

| Failure | Behavior |
|---|---|
| Mic permission denied | Toast + browser settings link; voice toggle reverts. |
| Mic disappears mid-session | Stop voice mode gracefully + toast. |
| Realtime upstream drops | Toast; stop playback; revert to idle. **No auto-reconnect** for voice — disrupting an active conversation with a reconnect is worse UX than stopping. |
| Audio playback underrun | Insert 20 ms silence; emit `warning` if >3 in a row. |
| Voice tool call fails | Tool result with `error` flows upstream normally; model speaks apology; ✗ tool card in UI. |
| Barge-in detected | Auto-clear playback queue; send `response.cancel` upstream. |
| Tab backgrounded | Keep WS open; playback continues; no auto-pause. |

### 9.3 Provider errors (both modes)

- 401/403 → banner "API key invalid for `<provider>`" + modal helping locate `.env`.
- 429 → toast "Rate limited — wait a moment"; no auto-retry.
- Other → generic toast with the provider's error message.

### 9.4 History coherence

- Voice and text turns land in the **same** JSONL; `voice: true` is UI metadata only.
- Resume into voice from text-only session: last ~20 turns injected as Realtime conversation items on `hello`.
- Mode switching mid-turn: blocked at the UI level.

### 9.5 Cancellation across the wire

- Text: client sends `cancel` → server calls `ChatSession.cancel_current()` (existing primitive).
- Voice: client sends `cancel` → server cancels shared `CancelToken` (interrupts any in-flight tool) AND sends `response.cancel` upstream.
- **One Esc keypress** triggers cancel for active mode. **Two presses within 2 s** in voice mode exits voice mode (mirrors CLI "two Ctrl+C exits within 2 s").

### 9.6 CSRF / origin

FastAPI checks `Origin` on WS upgrade (`localhost:5173` and `localhost:8000` in dev). Production: same-origin SPA, no tokens (single-user local).

---

## 10. Testing

### 10.1 Backend (`tests/`)

`tests/test_ws_text_protocol.py` — FastAPI `TestClient` + `FakeProvider`:

- `test_hello_starts_new_session`
- `test_user_message_streams_tokens`
- `test_tool_call_emits_canonical_events`
- `test_cancel_unwinds_cleanly`
- `test_resume_replays_history`
- `test_invalid_message_returns_error`

`tests/test_ws_voice_relay.py` — `FakeRealtimeWS` monkeypatched in:

- `test_audio_binary_passthrough`
- `test_transcript_delta_maps_to_client_event`
- `test_assistant_audio_forwarded`
- `test_tool_call_dispatches_and_responds_upstream`
- `test_speech_started_clears_playback`
- `test_cancel_propagates_upstream_and_clears`
- `test_voice_transcript_persists_to_jsonl`

### 10.2 Frontend (`web-ui/src/state/store.test.ts`, Vitest)

- `text_delta accumulates into the streaming assistant message`
- `tool_use events move through pendingTools and resolve`
- `cancel marks the streaming assistant message cancelled`

### 10.3 Manual smoke checklist

1. Text mode happy path.
2. Provider switch mid-session.
3. Cancel mid-stream (Esc).
4. Resume from sidebar.
5. Voice mode round-trip (toggle, ask, hear answer).
6. Voice barge-in (talk over the assistant).
7. Voice tool call (ask aloud to research a topic).
8. WS drop recovery (kill server, send, restart).

### 10.4 Deliberately out of scope

- No Playwright / browser e2e.
- No live OpenAI Realtime tests.
- No load tests.
- No accessibility audit.

---

## 11. Extension points

- **New tool** — existing pattern in `tools/`; available in both modes automatically via the shared registry.
- **New LLM provider** — existing `Provider` Protocol; text mode picks it up via the dropdown.
- **New voice (Realtime voice option)** — add to `voiceName` enum in the store + WS protocol.
- **Production deployment** — Dockerfile builds the SPA and bundles it under FastAPI static files; one container.
- **Multi-user** — would need auth middleware on FastAPI + per-user history dirs. Out of scope here.

---

## 12. Open risks

| Risk | Mitigation |
|---|---|
| OpenAI Realtime API behavior drift (event names, audio formats) | The relay's event-translation layer is the only contact surface; covered by `test_ws_voice_relay.py` with a fake. |
| `AudioWorklet` browser compatibility quirks | Target Chrome/Edge/Safari latest; document Firefox as "may have audio glitches". |
| WebSocket origin check breaking in some local-dev setups | `ELYOS_DEV_ORIGINS` env var lets the user add origins. |
| Time budget — three voice features is a real lift | OpenAI Realtime does the hard parts (VAD, turn-taking, interrupt). Our code is glue. |
| Concurrent tabs writing to the same JSONL | `BroadcastChannel` warning; last-write-wins is acceptable for single-user local. |
| Browser SpeechSynthesis voice quality varies | Voice mode (Realtime) is the high-quality path; text-mode TTS is a free "nice-to-have". |

---

## 13. Deliverables checklist

- [ ] `web/` package with FastAPI server, both WS handlers, sessions endpoint.
- [ ] `web-ui/` Vite app with sidebar + chat pane + composer + voice bar.
- [ ] Voice mode round-trip working against OpenAI Realtime.
- [ ] Sessions list shared with the CLI (same JSONL files).
- [ ] Backend smoke tests for WS protocol + voice relay translation.
- [ ] Frontend smoke tests for store behavior.
- [ ] `scripts/run_web.sh` dev launcher.
- [ ] Updated README with web-mode setup, usage, manual smoke checklist.
