"""Contract checks for the public Worker /mcp rate limits.

The Worker is TypeScript; this file only locks the agreed numbers and the
429 shape so CI notices drift without a Wrangler test harness.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WORKER = REPO / "workers" / "mcp"


def _wrangler() -> dict[str, object]:
    return tomllib.loads((WORKER / "wrangler.toml").read_text(encoding="utf-8"))


def _ratelimits() -> dict[str, dict[str, object]]:
    raw = _wrangler()["ratelimits"]
    assert isinstance(raw, list)
    named: dict[str, dict[str, object]] = {}
    for item in raw:
        assert isinstance(item, dict)
        name = item["name"]
        assert isinstance(name, str)
        named[name] = item
    return named


def test_wrangler_binds_minute_and_burst_limits() -> None:
    limits = _ratelimits()
    assert limits["MCP_RATE_LIMIT"]["simple"] == {"limit": 60, "period": 60}
    assert limits["MCP_BURST_LIMIT"]["simple"] == {"limit": 20, "period": 10}
    assert limits["MCP_RATE_LIMIT"]["namespace_id"] != limits["MCP_BURST_LIMIT"]["namespace_id"]


def test_handler_enforces_limits_only_on_mcp() -> None:
    handler = (WORKER / "src" / "index.ts").read_text(encoding="utf-8")
    health_idx = handler.index('url.pathname === "/health"')
    mcp_idx = handler.index('url.pathname === "/mcp"')
    limit_idx = handler.index("await enforceMcpRateLimits")
    assert health_idx < mcp_idx < limit_idx
    health_block = handler[health_idx:mcp_idx]
    assert "enforceMcpRateLimits" not in health_block


def test_rate_limit_response_is_sync_429() -> None:
    source = (WORKER / "src" / "rateLimit.ts").read_text(encoding="utf-8")
    assert "error: RATE_LIMITED_ERROR" in source or 'error: "rate_limited"' in source
    assert "rate_limited" in source
    assert "retry-after" in source
    assert "status: 429" in source
    assert "Queues" not in source


def test_landing_states_fair_use() -> None:
    html = (WORKER / "public" / "index.html").read_text(encoding="utf-8")
    assert "60 req/min" in html
    assert "API key" in html
    assert "execução de código" in html
    assert "429" in html
    assert "Retry-After" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_rate_limit_helpers_execute_in_node() -> None:
    result = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--test",
            str(WORKER / "src" / "rateLimit.test.ts"),
        ],
        cwd=WORKER,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
