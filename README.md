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

## Web UI

A browser-based UI with streaming chat, sessions sidebar, and voice mode (STT + TTS + barge-in) backed by OpenAI Realtime.

### Setup

```bash
# Backend (Python, reuses existing venv)
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd web-ui
npm install
cd ..
```

### Run (dev)

```bash
./scripts/run_web.sh
# FastAPI on :8000, Vite on :5173 — open http://localhost:5173
```

### Run (production-style)

```bash
cd web-ui && npm run build && cd ..
uvicorn web.server:app --port 8000
# Open http://localhost:8000 (FastAPI serves the built SPA)
```

### Voice mode

1. Set `OPENAI_API_KEY` in `.env` (Realtime API requires an OpenAI key regardless of which text provider is active).
2. Click the mic icon in the top bar. Allow microphone access.
3. Speak — Realtime's server-side VAD handles turn-taking. To interrupt the assistant mid-reply, just start talking ("barge-in").
4. Press Esc once to cancel the current reply; press the stop button (or Esc twice within 2s) to exit voice mode.

### Tests

```bash
# Backend
pytest -v

# Frontend
cd web-ui && npm test
```

### Manual smoke (web)

1. Text happy path — ask about weather, see tool spinner → result → streamed answer.
2. Provider switch mid-session — change Anthropic → OpenAI in top bar, next turn uses OpenAI (check server logs).
3. Cancel mid-stream — Esc during a long response.
4. Resume from sidebar — refresh, click a session.
5. Voice mode round-trip — toggle mic, ask aloud, hear answer.
6. Voice barge-in — talk over the assistant; it stops.
7. Voice tool call — say "research solar energy briefly"; spinner + result + spoken answer.
8. WS drop recovery — kill server, send a message, restart server.
