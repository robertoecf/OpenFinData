"""Origin token is required when MCP code mode is on."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from findata.api.app import app
from findata.api.origin_guard import (
    ORIGIN_TOKEN_HEADER,
    assert_code_mode_origin_configured,
    origin_token_authorized,
)


def test_code_mode_off_allows_requests_without_origin_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FINDATA_MCP_CODE_MODE", raising=False)
    monkeypatch.delenv("FINDATA_MCP_ORIGIN_TOKEN", raising=False)
    assert_code_mode_origin_configured()
    assert origin_token_authorized(None) is True


def test_code_mode_refuses_to_start_without_origin_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINDATA_MCP_CODE_MODE", "1")
    monkeypatch.delenv("FINDATA_MCP_ORIGIN_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="FINDATA_MCP_ORIGIN_TOKEN"):
        assert_code_mode_origin_configured()


def test_code_mode_rejects_missing_or_wrong_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINDATA_MCP_CODE_MODE", "1")
    monkeypatch.setenv("FINDATA_MCP_ORIGIN_TOKEN", "origin-secret")
    assert_code_mode_origin_configured()
    assert origin_token_authorized(None) is False
    assert origin_token_authorized("wrong") is False
    assert origin_token_authorized("origin-secret") is True


def test_code_mode_http_requires_origin_token_except_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINDATA_MCP_CODE_MODE", "1")
    monkeypatch.setenv("FINDATA_MCP_ORIGIN_TOKEN", "origin-secret")
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    denied = client.get("/stats")
    assert denied.status_code == 401
    allowed = client.get("/stats", headers={ORIGIN_TOKEN_HEADER: "origin-secret"})
    assert allowed.status_code == 200
