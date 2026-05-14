"""Rich-based renderer for the canonical event stream."""
from __future__ import annotations
import json
from rich.console import Console
from rich.spinner import Spinner
from rich.live import Live


class Renderer:
    """Streams assistant text inline; shows a spinner during tool calls.

    Designed to be simple — no Live region juggling. Spinner appears as a
    line below the streamed text and is replaced by the tool result.
    """
    def __init__(self, console: Console | None = None):
        self.console = console or Console()
        self._spinner_live: Live | None = None
        self._has_written_text = False

    def write(self, text: str) -> None:
        if not self._has_written_text:
            self.console.print("[bold cyan]assistant:[/] ", end="")
            self._has_written_text = True
        self.console.print(text, end="", soft_wrap=True, highlight=False)

    def begin_tool(self, name: str) -> None:
        self._end_text_line()
        self._spinner_live = Live(
            Spinner("dots", text=f"[yellow]calling tool: {name}…[/]"),
            console=self.console,
            refresh_per_second=12,
            transient=True,
        )
        self._spinner_live.start()

    def end_tool(self, name: str, result: dict) -> None:
        if self._spinner_live is not None:
            self._spinner_live.stop()
            self._spinner_live = None
        is_error = bool(result.get("error"))
        tag = "[red]✗[/]" if is_error else "[green]✓[/]"
        summary = self._summarise(result)
        self.console.print(f"  {tag} [dim]{name}[/]: {summary}")

    def show_error(self, msg: str) -> None:
        self._end_text_line()
        if self._spinner_live is not None:
            self._spinner_live.stop()
            self._spinner_live = None
        self.console.print(f"[red][error][/] {msg}")

    def turn_done(self) -> None:
        self._end_text_line()
        self._has_written_text = False

    def cancelled(self) -> None:
        self._end_text_line()
        if self._spinner_live is not None:
            self._spinner_live.stop()
            self._spinner_live = None
        self.console.print("[yellow][cancelled][/]")

    def _end_text_line(self) -> None:
        if self._has_written_text:
            self.console.print()  # newline
            self._has_written_text = False

    def _summarise(self, result: dict) -> str:
        s = json.dumps(result, ensure_ascii=False)
        return s if len(s) <= 200 else s[:197] + "..."
