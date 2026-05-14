"""Shared dependencies for the FastAPI server.

One ToolRegistry + ToolHttpClient is shared across all WS connections —
identical to how the CLI app uses them.
"""
from __future__ import annotations
from pathlib import Path

from elyos_chat.config import Config
from elyos_chat.tools.http import ToolHttpClient
from elyos_chat.tools.registry import ToolRegistry
from elyos_chat.tools.research import RESEARCH_TOOL
from elyos_chat.tools.weather import WEATHER_TOOL


HISTORY_DIR = Path.home() / ".elyos_chat" / "sessions"


class AppState:
    def __init__(self):
        self.cfg: Config | None = None
        self.http: ToolHttpClient | None = None
        self.registry: ToolRegistry | None = None

    async def startup(self):
        self.cfg = Config.from_env()
        self.http = ToolHttpClient(base_url=self.cfg.api_base, api_key=self.cfg.api_key)
        self.registry = ToolRegistry(http=self.http)
        self.registry.register(WEATHER_TOOL)
        self.registry.register(RESEARCH_TOOL)

    async def shutdown(self):
        if self.http:
            await self.http.aclose()


state = AppState()
