"""API smoke tests using FastAPI's TestClient.

These tests use respx to mock outbound HTTP calls, so no real network is hit.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from findata.api.app import app
from findata.http_client import clear_cache


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
    assert body["name"] == "findata-br"
    assert "version" in body
    assert body["site"] == "/"
    assert "bcb" in body["sources"]
    assert "openfinance" in body["sources"]


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
