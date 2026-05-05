"""API smoke tests using FastAPI's TestClient.

These tests use respx to mock outbound HTTP calls, so no real network is hit.
"""

from __future__ import annotations

from html.parser import HTMLParser

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from findata.api.app import app
from findata.http_client import clear_cache


class _DocsHeadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.html_attrs: dict[str, str | None] = {}
        self.in_head = False
        self.description: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "html":
            self.html_attrs = attr_map
        elif tag == "head":
            self.in_head = True
        elif self.in_head and tag == "meta" and attr_map.get("name") == "description":
            self.description = attr_map.get("content")

    def handle_endtag(self, tag: str) -> None:
        if tag == "head":
            self.in_head = False


@pytest.fixture
def client() -> TestClient:
    clear_cache()
    return TestClient(app)


def test_root_endpoint(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "findata-br" in r.text
    assert "/site/site.css" in r.text
    assert "/docs" in r.text


def test_meta_endpoint(client: TestClient) -> None:
    r = client.get("/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Dados Financeiros Abertos"
    assert body["slug"] == "findata-br"
    assert (
        body["statement"] == "Infraestrutura open source para dados financeiros públicos do Brasil."
    )
    assert "version" in body
    assert body["site"] == "/"
    assert body["docs"] == "/docs"
    assert body["charts"] == "/charts"
    assert body["swagger"] == "/api/docs"
    assert "bcb" in body["sources"]
    assert "openfinance" in body["sources"]


def test_developer_docs_page(client: TestClient) -> None:
    r = client.get("/docs")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    parser = _DocsHeadParser()
    parser.feed(r.text)
    assert parser.html_attrs.get("lang") == "en"
    assert parser.description is not None
    assert "Developer console" in parser.description
    assert "REST API" in parser.description
    assert "OpenAPI schema" in parser.description
    assert "MCP endpoint" in parser.description
    assert "Console técnico" not in parser.description
    assert "Open chart lab" in r.text
    assert "/charts" in r.text
    assert "/api/docs" in r.text
    assert "/openapi.json" in r.text


def test_charts_page(client: TestClient) -> None:
    r = client.get("/charts")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "lightweight-charts@5.2.0" in r.text
    assert "integrity=" in r.text
    assert "/site/chart-explorer.js" in r.text
    assert "Visualizador beta" in r.text
    assert "produto principal continua sendo API" in r.text
    assert 'href="https://www.tradingview.com/lightweight-charts/"' in r.text
    assert "TradingView Lightweight Charts™" in r.text
    assert 'href="https://github.com/robertoecf/findata-br"' in r.text
    assert "%5EBVSP" not in r.text


def test_chart_explorer_asset(client: TestClient) -> None:
    r = client.get("/site/chart-explorer.js")
    assert r.status_code == 200
    assert "LightweightCharts" in r.text
    assert "attributionLogo: false" in r.text
    assert "bcbSeriesEndpoint(432, 24)" in r.text
    assert "MAX_POINTS = 5000" in r.text
    assert "REQUEST_TIMEOUT_MS = 15000" in r.text
    assert "new URL(rawEndpoint, window.location.origin)" in r.text
    assert "/tesouro/bonds/history" not in r.text
    assert 'options.type === "candlestick" || (!options.field && hasOhlc(firstRecord))' in r.text
    assert "timestampFromDate" in r.text
    assert "isValidDateParts" in r.text
    assert "parseCompactPeriod" in r.text
    assert "parseUnixTimestamp" in r.text
    assert "allowShortSeconds" in r.text
    assert "parseUnixTimestamp(text, { allowShortSeconds: true })" in r.text
    assert "unixTimestamp !== null" in r.text
    assert "normalizeMixedTimes" in r.text
    assert "normalizedTime.hasIntraday ? a.time - b.time : a.time.localeCompare(b.time)" in r.text
    assert "timeVisible: normalized.hasIntraday" in r.text
    assert "Yahoo Finance" not in r.text


def test_swagger_ui_moved_to_api_docs(client: TestClient) -> None:
    r = client.get("/api/docs")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "swagger-ui" in r.text


def test_stats_uses_same_source_registry_as_meta(client: TestClient) -> None:
    root_sources = client.get("/meta").json()["sources"]
    stats_sources = client.get("/stats").json()["sources"]
    assert stats_sources == list(root_sources)


def test_health_endpoint(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_bcb_list_series(client: TestClient) -> None:
    r = client.get("/bcb/series")
    assert r.status_code == 200
    catalog = r.json()
    assert "selic" in catalog
    assert catalog["selic"]["code"] == 432


def test_bcb_focus_indicators(client: TestClient) -> None:
    r = client.get("/bcb/focus/indicators")
    assert r.status_code == 200
    assert "IPCA" in r.json()


def test_ibge_list_indicators(client: TestClient) -> None:
    r = client.get("/ibge/indicators")
    assert r.status_code == 200
    assert "ipca_mensal" in r.json()


def test_ibge_ipca_groups(client: TestClient) -> None:
    r = client.get("/ipca/groups") if False else client.get("/ibge/ipca/groups")
    assert r.status_code == 200
    groups = r.json()
    assert "7169" in groups


def test_unknown_series_returns_400(client: TestClient) -> None:
    r = client.get("/bcb/series/name/nonexistent-xyz")
    assert r.status_code == 400
    assert "Unknown series" in r.json()["detail"]


def test_focus_unknown_indicator_returns_400(client: TestClient) -> None:
    r = client.get("/bcb/focus/annual", params={"indicator": "HACKED' or 1"})
    assert r.status_code == 400


@respx.mock
def test_bcb_series_name_happy_path(client: TestClient) -> None:
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/3").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"data": "20/04/2026", "valor": "11.25"},
                {"data": "21/04/2026", "valor": "11.25"},
                {"data": "22/04/2026", "valor": "11.25"},
            ],
        )
    )
    r = client.get("/bcb/series/name/selic", params={"n": 3})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3
    assert data[0]["valor"] == 11.25
