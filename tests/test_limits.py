"""Unit and exception-path tests for API rate limiting."""

from __future__ import annotations

import pytest
from fastapi import Request
from limits import parse
from slowapi.wrappers import Limit

from findata import _limits
from findata.api.app import app


def _request(*, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers or [],
            "client": ("192.0.2.10", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
            "app": app,
        }
    )


def test_client_id_prefers_first_forwarded_address() -> None:
    request = _request(headers=[(b"x-forwarded-for", b"198.51.100.7, 203.0.113.9")])
    assert _limits._client_id(request) == "198.51.100.7"


def test_client_id_falls_back_to_remote_address() -> None:
    assert _limits._client_id(_request()) == "192.0.2.10"


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_limits_enabled_accepts_truthy_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("FINDATA_RATE_LIMIT_ENABLED", value)
    assert _limits._limits_enabled() is True


def test_limits_enabled_rejects_other_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINDATA_RATE_LIMIT_ENABLED", "false")
    assert _limits._limits_enabled() is False


def test_default_limits_reads_and_splits_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINDATA_RATE_LIMIT_DEFAULT", " 2/second ; 10/minute; ")
    assert _limits._default_limits() == ["2/second", "10/minute"]


def test_rate_limit_exception_handler_returns_429_json() -> None:
    """Exercise the registered handler without mutating the global app routes."""
    rate_item = parse("1/minute")
    limit = Limit(rate_item, _limits._client_id, None, False, None, None, None, 1, False)
    request = _request(headers=[(b"x-forwarded-for", b"198.51.100.211")])
    request.state.view_rate_limit = (rate_item, ["198.51.100.211"])

    response = _limits._rate_limit_exceeded_handler(
        request,
        _limits.RateLimitExceeded(limit),
    )

    assert response.status_code == 429
    assert b"Rate limit exceeded:" in response.body
