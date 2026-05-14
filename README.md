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
