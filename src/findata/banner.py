"""Animated CLI banner — DADOS FINANCEIROS ABERTOS typed out with a gradient."""

from __future__ import annotations

import sys
import time

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

_ASCII = r"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ Dados Financeiros Abertos                                                  ║
║ Dados financeiros públicos do Brasil                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# Brazil-flag-inspired gradient: green → yellow → blue
_GRADIENT = [
    "#009c3b",
    "#0ea848",
    "#2db84f",
    "#55c258",
    "#8bcf5a",
    "#ffd400",
    "#ffe100",
    "#ffee00",
    "#ffd400",
    "#f5b400",
    "#3a8fe0",
    "#2a7fd5",
    "#1a6fd0",
    "#0a5fc5",
    "#002776",
]


def _gradient_line(line: str, offset: int = 0) -> Text:
    t = Text()
    n = len(_GRADIENT)
    for i, ch in enumerate(line):
        if ch == " ":
            t.append(ch)
        else:
            t.append(ch, style=f"bold {_GRADIENT[(i + offset) % n]}")
    return t


def render_static_banner(console: Console | None = None) -> None:
    """Render a static (non-animated) gradient banner. Safe for non-TTY."""
    console = console or Console()
    lines = [ln for ln in _ASCII.splitlines() if ln.strip()]
    text = Text()
    for i, line in enumerate(lines):
        text.append_text(_gradient_line(line, offset=i * 2))
        text.append("\n")
    tagline = Text(
        "  API · MCP · CLI  •  BCB · CVM · B3 · IBGE · IPEA · Tesouro",
        style="italic dim",
    )
    console.print(Align.center(text))
    console.print(Align.center(tagline))


def render_animated_banner(
    console: Console | None = None,
    char_delay: float = 0.002,
    final_pause: float = 0.15,
) -> None:
    """Typewriter-style animated banner with gradient. No-op when not a TTY."""
    console = console or Console()
    if not sys.stdout.isatty():
        render_static_banner(console)
        return

    lines = [ln for ln in _ASCII.splitlines() if ln.strip()]
    # Clear a little vertical space
    console.print()

    # Progressive reveal, line-by-line, char-by-char.
    # We use raw writes for fluid output, then emit the final rich version.
    for i, line in enumerate(lines):
        buffer = ""
        for ch in line:
            buffer += ch
            sys.stdout.write(ch)
            sys.stdout.flush()
            if ch != " ":
                time.sleep(char_delay)
        sys.stdout.write("\n")
        sys.stdout.flush()
        # Replace the line with the gradient-coloured version in place
        sys.stdout.write("\033[F\033[2K")  # move up, clear line
        console.print(_gradient_line(line, offset=i * 2))

    tagline = Text(
        "  API · MCP · CLI  •  BCB · CVM · B3 · IBGE · IPEA · Tesouro",
        style="italic dim",
    )
    console.print(tagline)
    time.sleep(final_pause)


def render_startup_panel(host: str, port: int, mcp_enabled: bool = True) -> Panel:
    body = Text()
    body.append("  REST API  ", style="bold")
    body.append(f"http://{host}:{port}/docs\n", style="cyan underline")
    if mcp_enabled:
        body.append("  MCP       ", style="bold")
        body.append(f"http://{host}:{port}/mcp\n", style="magenta underline")
    body.append("  Health    ", style="bold")
    body.append(f"http://{host}:{port}/health", style="green underline")
    return Panel(
        body,
        title="[bold]Dados Financeiros Abertos running[/bold]",
        border_style="#009c3b",
        padding=(1, 2),
    )
