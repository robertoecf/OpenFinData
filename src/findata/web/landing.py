"""Render the Python-served findata-br landing page."""

from __future__ import annotations

from html import escape
from pathlib import Path

from fastapi.responses import HTMLResponse

_WEB_DIR = Path(__file__).resolve().parent
WEB_STATIC_DIR = _WEB_DIR / "static"
_LANDING_TEMPLATE_PATH = _WEB_DIR / "templates" / "index.html"
_DOCS_TEMPLATE_PATH = _WEB_DIR / "templates" / "docs.html"


def _render_template(
    template_path: Path,
    *,
    version: str,
    sources: dict[str, str],
    mcp_enabled: bool,
) -> HTMLResponse:
    """Return a static web template with small runtime facts injected."""
    html = template_path.read_text(encoding="utf-8")
    replacements = {
        "{{ version }}": escape(version),
        "{{ source_count }}": str(len(sources)),
        "{{ mcp_status }}": "ativo" if mcp_enabled else "indisponível",
    }
    for token, value in replacements.items():
        html = html.replace(token, value)
    return HTMLResponse(html)


def render_landing_page(
    *,
    version: str,
    sources: dict[str, str],
    mcp_enabled: bool,
) -> HTMLResponse:
    """Return the public landing page."""
    return _render_template(
        _LANDING_TEMPLATE_PATH,
        version=version,
        sources=sources,
        mcp_enabled=mcp_enabled,
    )


def render_developer_page(
    *,
    version: str,
    sources: dict[str, str],
    mcp_enabled: bool,
) -> HTMLResponse:
    """Return the custom developer console page."""
    return _render_template(
        _DOCS_TEMPLATE_PATH,
        version=version,
        sources=sources,
        mcp_enabled=mcp_enabled,
    )
