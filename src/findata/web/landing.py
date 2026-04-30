"""Render the Python-served findata-br landing page."""

from __future__ import annotations

from html import escape
from pathlib import Path

from fastapi.responses import HTMLResponse

_WEB_DIR = Path(__file__).resolve().parent
WEB_STATIC_DIR = _WEB_DIR / "static"
_TEMPLATE_PATH = _WEB_DIR / "templates" / "index.html"


def render_landing_page(
    *,
    version: str,
    sources: dict[str, str],
    mcp_enabled: bool,
) -> HTMLResponse:
    """Return the static landing page with small runtime facts injected."""
    html = _TEMPLATE_PATH.read_text(encoding="utf-8")
    replacements = {
        "{{ version }}": escape(version),
        "{{ source_count }}": str(len(sources)),
        "{{ mcp_status }}": "ativo" if mcp_enabled else "indisponível",
    }
    for token, value in replacements.items():
        html = html.replace(token, value)
    return HTMLResponse(html)
