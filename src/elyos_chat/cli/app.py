"""CLI entrypoint: input loop, SIGINT handler, provider/tool wiring."""
from __future__ import annotations
import argparse
import asyncio
import signal
import time
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console

from elyos_chat.chat.history import History
from elyos_chat.chat.session import ChatSession
from elyos_chat.cli.renderer import Renderer
from elyos_chat.config import Config
from elyos_chat.tools.http import ToolHttpClient
from elyos_chat.tools.registry import ToolRegistry
from elyos_chat.tools.research import RESEARCH_TOOL
from elyos_chat.tools.weather import WEATHER_TOOL


HISTORY_DIR = Path.home() / ".elyos_chat" / "sessions"
DEFAULT_SYSTEM = (
    "You are a helpful assistant. You have two tools: weather (fast) and "
    "research (slow, 3-8s). Prefer calling tools when the user asks about "
    "real-world facts. Tool errors are returned as JSON with 'error' and "
    "'guidance' fields — read them and decide how to proceed."
)


def _build_provider(cfg: Config):
    if cfg.provider == "anthropic":
        from elyos_chat.providers.anthropic import AnthropicProvider
        return AnthropicProvider(model=cfg.model)
    if cfg.provider == "openai":
        from elyos_chat.providers.openai import OpenAIProvider
        return OpenAIProvider(model=cfg.model)
    if cfg.provider == "gemini":
        from elyos_chat.providers.gemini import GeminiProvider
        return GeminiProvider(model=cfg.model)
    raise SystemExit(f"unsupported provider: {cfg.provider}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="elyos-chat", description="Streaming CLI chat with Elyos tools.")
    p.add_argument("--provider", help="Override ELYOS_PROVIDER (anthropic|openai|gemini)")
    p.add_argument("--model", help="Override ELYOS_MODEL")
    p.add_argument("--resume", help="Resume a session by id, or 'last' for the most recent")
    p.add_argument("--system", help="Path to a system-prompt file")
    return p.parse_args(argv)


async def _amain(args: argparse.Namespace) -> int:
    console = Console()
    cfg = Config.from_env()
    if args.provider:
        cfg.provider = args.provider
    if args.model:
        cfg.model = args.model

    system = DEFAULT_SYSTEM
    if args.system:
        system = Path(args.system).read_text()

    provider = _build_provider(cfg)
    http = ToolHttpClient(base_url=cfg.api_base, api_key=cfg.api_key)
    registry = ToolRegistry(http=http)
    registry.register(WEATHER_TOOL)
    registry.register(RESEARCH_TOOL)

    if args.resume == "last":
        history = History.resume_last(HISTORY_DIR) or History.new(HISTORY_DIR)
    elif args.resume:
        history = History.resume(HISTORY_DIR, args.resume)
    else:
        history = History.new(HISTORY_DIR)

    renderer = Renderer(console=console)
    session = ChatSession(provider=provider, registry=registry,
                          history=history, renderer=renderer, system=system)

    console.print(f"[dim]elyos-chat — provider={cfg.provider} model={provider.model} session={history.session_id}[/]")
    console.print("[dim]Ctrl+C cancels a running turn. Two Ctrl+Cs at the prompt within 2s exits.[/]\n")

    loop = asyncio.get_running_loop()
    last_sigint = {"t": 0.0}

    def on_sigint():
        # If a turn is in flight, cancel it. Otherwise, double-tap to exit.
        if session._cancel is not None:
            session.cancel_current()
            renderer.cancelled()
        else:
            now = time.monotonic()
            if now - last_sigint["t"] < 2.0:
                console.print("[dim]bye[/]")
                loop.stop()
            else:
                console.print("[dim]Press Ctrl+C again within 2s to exit.[/]")
                last_sigint["t"] = now

    loop.add_signal_handler(signal.SIGINT, on_sigint)

    prompt = PromptSession()
    try:
        with patch_stdout():
            while True:
                try:
                    text = await prompt.prompt_async("you> ")
                except (EOFError, KeyboardInterrupt):
                    break
                if not text.strip():
                    continue
                if text.strip() in {"/exit", "/quit"}:
                    break
                await session.handle_user_input(text.strip())
    finally:
        await http.aclose()
    return 0


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_amain(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
