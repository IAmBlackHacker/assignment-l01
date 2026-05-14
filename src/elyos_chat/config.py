"""Environment-based configuration.

Reads ELYOS_PROVIDER, ELYOS_MODEL, ELYOS_API_BASE, ELYOS_API_KEY, plus
the provider-specific key. Fails fast with a clear message.
"""
from __future__ import annotations
import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    provider: str
    model: str | None
    api_base: str
    api_key: str

    @classmethod
    def from_env(cls) -> "Config":
        provider = os.environ.get("ELYOS_PROVIDER", "anthropic").lower()
        model = os.environ.get("ELYOS_MODEL") or None
        api_base = os.environ.get(
            "ELYOS_API_BASE",
            "https://elyos-interview-907656039105.europe-west2.run.app",
        )
        api_key = os.environ.get("ELYOS_API_KEY")
        if not api_key:
            _fail("ELYOS_API_KEY is not set. Copy .env.example to .env and fill it in.")

        # Validate the provider's own key is present.
        required = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }
        if provider not in required:
            _fail(f"Unknown ELYOS_PROVIDER='{provider}'. Use one of: anthropic, openai, gemini.")
        if not os.environ.get(required[provider]):
            _fail(f"ELYOS_PROVIDER={provider} requires {required[provider]} to be set.")

        return cls(provider=provider, model=model, api_base=api_base, api_key=api_key)


def _fail(msg: str) -> None:
    print(f"config error: {msg}", file=sys.stderr)
    sys.exit(2)
