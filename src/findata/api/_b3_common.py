"""Shared B3 live-quote helpers for the REST and MCP layers.

``yfinance`` is imported lazily so the rest of the API keeps working without
the optional ``[b3]`` extra installed. Both ``routers/b3.py`` and ``mcp_app.py``
resolve the quotes module through here, so the install hint lives in one place.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

MAX_TICKERS = 20


def resolve_quotes() -> Any:
    """Return the yfinance-backed quotes module, or raise 503 if the extra is missing."""
    try:
        from findata.sources.b3 import quotes
    except ImportError as exc:  # pragma: no cover - only without the [b3] extra
        raise HTTPException(
            status_code=503,
            detail="B3 live quotes need the optional extra: pip install 'openfindata[b3]'",
        ) from exc
    return quotes
