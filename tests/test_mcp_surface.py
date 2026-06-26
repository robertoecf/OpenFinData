"""Tests for the curated MCP surface (findata.api.mcp_app).

Guards the three promises of the MCP curation:
  1. the tool catalog is small and curated, not 1:1 with the 95 REST routes,
  2. the public REST API still exposes all 95 routes (curation is MCP-only),
  3. consolidated tools dispatch by their ``dataset``/``kind`` selector and
     validate bad combinations with a 400.

All assertions are offline, no live gov-API calls.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from findata.api.app import app
from findata.api.mcp_app import mcp_app

EXPECTED_TOOLS = 24  # curated tools with code mode OFF (the default)
EXPECTED_REST_OPERATIONS = 95  # all REST routes (unconditional); bump when the surface changes

_HTTP_METHODS = {"get", "post", "put", "delete", "patch"}


def _operation_ids(fastapi_app: object) -> set[str]:
    ids: set[str] = set()
    for path, methods in fastapi_app.openapi()["paths"].items():  # type: ignore[attr-defined]
        for method, spec in methods.items():
            if method in _HTTP_METHODS:
                ids.add(spec.get("operationId") or f"{method} {path}")
    return ids


# ── catalog size & REST integrity ──────────────────────────────────


def test_curated_mcp_is_a_small_fraction_of_the_rest_surface() -> None:
    mcp_ids = _operation_ids(mcp_app)
    rest_ids = _operation_ids(app)
    assert len(mcp_ids) == EXPECTED_TOOLS
    assert len(rest_ids) == EXPECTED_REST_OPERATIONS
    # the whole point of curation: catalog << REST surface
    assert len(mcp_ids) < len(rest_ids) // 3


def test_rest_api_untouched_by_curation() -> None:
    # the consolidated REST routes that MCP tools fold together must still exist,
    # they back the CLI and HTTP consumers.
    paths = set(app.openapi()["paths"])
    for p in (
        "/bcb/ptax/usd/period",
        "/bcb/focus/selic",
        "/cvm/funds/holdings",
        "/cvm/funds/fidc/direitos-creditorios",
    ):
        assert p in paths, f"REST route {p} disappeared"


def test_mcp_transport_mounted_on_public_app() -> None:
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/mcp" in paths


def test_every_tool_has_an_agent_oriented_summary() -> None:
    for _path, methods in mcp_app.openapi()["paths"].items():
        for method, spec in methods.items():
            if method not in _HTTP_METHODS:
                continue
            summary = spec.get("summary", "")
            # a real description, not the auto-generated "GET /path"
            assert summary and not summary.startswith(("GET ", "POST "))
            assert len(summary) > 20


# ── consolidated-tool dispatch (offline) ───────────────────────────


def test_bcb_series_lists_catalog_with_no_args() -> None:
    r = TestClient(mcp_app).get("/bcb/series")
    assert r.status_code == 200
    assert len(r.json()) > 10  # the curated SGS catalog


def test_registry_lookup_resolves_ticker_offline() -> None:
    r = TestClient(mcp_app).get("/registry/lookup", params={"q": "PETR4", "limit": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["entities"], "expected at least one match for PETR4"
    assert body["entities"][0]["cnpj"].startswith("33.000.167")


def test_consolidated_tool_validates_missing_selector_args() -> None:
    # cvm_company dataset=filings requires `year` -> 400 (not a 500)
    r = TestClient(mcp_app).get("/cvm/company", params={"dataset": "filings"})
    assert r.status_code == 400
    assert "year" in r.json()["detail"]


def test_cvm_fund_holdings_requires_cnpj_and_month() -> None:
    r = TestClient(mcp_app).get("/cvm/fund", params={"dataset": "holdings", "year": 2024})
    assert r.status_code == 400
    assert "cnpj" in r.json()["detail"]


# ── code-mode gating ───────────────────────────────────────────────


def test_code_mode_is_off_by_default() -> None:
    assert "findata_run_code" not in _operation_ids(mcp_app)


def test_code_mode_registers_tool_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINDATA_MCP_CODE_MODE", "1")
    import findata.api.mcp_app as fresh

    reloaded = importlib.reload(fresh)
    try:
        assert "findata_run_code" in _operation_ids(reloaded.mcp_app)
    finally:
        # restore the canonical (code-mode off) module for any later imports
        monkeypatch.delenv("FINDATA_MCP_CODE_MODE", raising=False)
        importlib.reload(fresh)


# -- added validations (offline) ------------------------------------


def test_siconfi_rgf_rejects_out_of_range_period() -> None:
    # RGF is the quadrimestre 1-3; period 6 is valid only for RREO bimestre.
    r = TestClient(mcp_app).get(
        "/tesouro/siconfi",
        params={"report": "rgf", "year": 2024, "period": 6, "cod_ibge": 1},
    )
    assert r.status_code == 400
    assert "1-3" in r.json()["detail"]


def test_focus_rejects_top5_monthly() -> None:
    # Top-5 panel exists only for the annual horizon.
    r = TestClient(mcp_app).get("/bcb/focus", params={"panel": "top5", "horizon": "monthly"})
    assert r.status_code == 400


def test_structured_fund_fip_rejects_dataset() -> None:
    # FIP has no dataset facet; passing one is a client error, not silently ignored.
    r = TestClient(mcp_app).get(
        "/cvm/structured-fund", params={"kind": "fip", "year": 2024, "dataset": "geral"}
    )
    assert r.status_code == 400
