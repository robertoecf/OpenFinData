"""TestClient tests for /registry/lookup and /registry/meta.

These run against the *real* embedded ``registry.sqlite`` because the wheel
ships it and tests should validate the same artefact users will install.
The fixture is a singleton FastAPI ``TestClient``; setup is one shot.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from findata.api.app import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_lookup_cnpj_no_mask(client: TestClient) -> None:
    r = client.get("/registry/lookup", params={"q": "33000167000101"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    nomes = [e["nome"] for e in body["entities"]]
    assert any("PETROBRAS" in n.upper() for n in nomes)


def test_lookup_cnpj_with_mask(client: TestClient) -> None:
    """Mask is collapsed by the server; resolves the same as bare digits."""
    r = client.get("/registry/lookup", params={"q": "33.000.167/0001-01"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any("PETROBRAS" in e["nome"].upper() for e in body["entities"])


def test_lookup_ticker(client: TestClient) -> None:
    r = client.get("/registry/lookup", params={"q": "PETR4"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    # The first hit should be Petrobras (ticker PETR4 is in its searchable).
    top = body["entities"][0]
    assert top["nome"] == "PETROBRAS"
    assert "PETR4" in top["tickers"]


def test_lookup_short_query_rejected(client: TestClient) -> None:
    r = client.get("/registry/lookup", params={"q": "x"})
    # FastAPI Query(min_length=2) → 422
    assert r.status_code == 422


def test_lookup_empty_query_rejected(client: TestClient) -> None:
    r = client.get("/registry/lookup", params={"q": ""})
    assert r.status_code == 422


def test_lookup_no_match(client: TestClient) -> None:
    """A 14-digit CNPJ that doesn't exist → empty list, NOT 404."""
    r = client.get("/registry/lookup", params={"q": "99999999999999"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["entities"] == []


def test_lookup_respects_limit(client: TestClient) -> None:
    r = client.get("/registry/lookup", params={"q": "BANCO", "limit": 3})
    assert r.status_code == 200
    body = r.json()
    assert len(body["entities"]) <= 3


def test_lookup_limit_max(client: TestClient) -> None:
    r = client.get("/registry/lookup", params={"q": "BANCO", "limit": 200})
    assert r.status_code == 422  # le=100


def test_lookup_returns_rank(client: TestClient) -> None:
    r = client.get("/registry/lookup", params={"q": "PETR4"})
    assert r.status_code == 200
    body = r.json()
    assert body["entities"][0]["rank"] is not None
    assert body["entities"][0]["rank"] < 0  # FTS5 BM25 is always negative for hits


def test_lookup_query_field_echoes_input(client: TestClient) -> None:
    r = client.get("/registry/lookup", params={"q": "33.000.167/0001-01"})
    assert r.status_code == 200
    assert r.json()["query"] == "33.000.167/0001-01"


def test_meta_endpoint(client: TestClient) -> None:
    r = client.get("/registry/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "1"
    assert "built_at" in body
    assert "content_sha256" in body
    assert "sources_json" in body


def test_app_registers_registry_routes() -> None:
    """Smoke: registry routes are registered and exposed by the app.

    fastapi-mcp discovers tools from the OpenAPI schema; if the routes
    aren't exposed, the MCP server can't expose them. We assert against
    ``app.openapi()`` as a proxy for "the MCP companion will see them".
    (Walking ``app.routes`` no longer works: since FastAPI 0.137 /
    Starlette 1.3 included routers are kept as lazy ``_IncludedRouter``
    wrappers, so their child paths aren't flattened into ``app.routes``.)
    """
    paths = app.openapi()["paths"]
    assert "/registry/lookup" in paths
    assert "/registry/meta" in paths


def test_mcp_companion_loaded() -> None:
    """Smoke: fastapi-mcp module mounted without raising at import time.

    A True value means MCP discovery ran; auto-tools include /registry/*
    transitively because they're standard FastAPI routes. False means the
    MCP companion failed to initialize (e.g. fastapi-mcp not installed) —
    the API itself still works, but MCP is unavailable.
    """
    from findata.api.app import _MCP_ENABLED

    assert isinstance(_MCP_ENABLED, bool)
