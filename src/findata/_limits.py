"""Rate limiting for the public-facing API.

Dados Financeiros Abertos is read-only and talks only to free public sources, so the limits
exist to protect *upstream* (BCB/CVM/IBGE/IPEA/Tesouro/yfinance) and *us*
from abusive clients — not to gate access.

All knobs are env-var driven, so a WSL deploy behind Cloudflare Tunnel can
tune without a code change:

    FINDATA_RATE_LIMIT_DEFAULT="60/minute;1000/day"
    FINDATA_RATE_LIMIT_ENABLED="true"

Rate-limit keying uses `X-Forwarded-For` when present (Cloudflare/NGINX set
it), otherwise the remote address.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from fastapi import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

_DEFAULT_LIMIT = "60/minute;1000/day"


def _client_id(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _limits_enabled() -> bool:
    return os.environ.get("FINDATA_RATE_LIMIT_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _default_limits() -> list[str | Callable[..., str]]:
    value = os.environ.get("FINDATA_RATE_LIMIT_DEFAULT", _DEFAULT_LIMIT)
    return [p.strip() for p in value.split(";") if p.strip()]


limiter = Limiter(
    key_func=_client_id,
    default_limits=_default_limits() if _limits_enabled() else [],
    headers_enabled=True,  # emit X-RateLimit-* headers for clients
)

__all__ = ["RateLimitExceeded", "_rate_limit_exceeded_handler", "limiter"]
