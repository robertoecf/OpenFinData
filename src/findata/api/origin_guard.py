"""Fail-closed origin token when MCP code mode is on.

Cloudflare Access sits at the edge. This check is the origin's own gate so a
misconfigured tunnel, a local port-forward, or a skipped Access policy cannot
reach ``findata_run_code``. Health probes stay exempt.
"""

from __future__ import annotations

import hmac
import os

ORIGIN_TOKEN_ENV = "FINDATA_MCP_ORIGIN_TOKEN"  # noqa: S105
ORIGIN_TOKEN_HEADER = "x-openfindata-origin-token"  # noqa: S105
_CODE_MODE_TRUTHY = frozenset({"1", "true", "yes", "on"})
_HEALTH_PATH = "/health"


def code_mode_enabled() -> bool:
    return os.getenv("FINDATA_MCP_CODE_MODE", "").strip().lower() in _CODE_MODE_TRUTHY


def configured_origin_token() -> str:
    return os.getenv(ORIGIN_TOKEN_ENV, "").strip()


def assert_code_mode_origin_configured() -> None:
    if code_mode_enabled() and not configured_origin_token():
        raise RuntimeError(
            "FINDATA_MCP_CODE_MODE is on but FINDATA_MCP_ORIGIN_TOKEN is empty. "
            "Refusing to start. Set a random origin token and inject it from "
            "the tunnel as X-Openfindata-Origin-Token."
        )


def is_health_path(path: str) -> bool:
    return path.rstrip("/") == _HEALTH_PATH


def origin_token_authorized(header_value: str | None) -> bool:
    if not code_mode_enabled():
        return True
    expected = configured_origin_token()
    provided = (header_value or "").strip()
    if not expected or not provided or len(provided) != len(expected):
        return False
    return hmac.compare_digest(provided, expected)
