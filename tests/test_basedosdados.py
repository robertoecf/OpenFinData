"""Base dos Dados integration tests (mocked; no live API calls)."""

from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from findata.api.app import app
from findata.http_client import clear_cache
from findata.sources.basedosdados import catalog


def test_source_info_marks_free_logged_in_not_anbima_like() -> None:
    info = catalog.source_info()
    assert info.status == "free_logged_in"
    access = {path.name: path.access for path in info.access_paths}
    assert access["SQL via BigQuery"] == "free_logged_in"
    assert access["Python SDK"] == "free_logged_in"
    assert access["R package"] == "free_logged_in"
    assert access["BD Pro"] == "paid_logged_in"
    assert any("Different from ANBIMA" in note for note in info.notes)


def test_table_ref_builds_bigquery_sql() -> None:
    ref = catalog.table_ref("br_bd_diretorios_brasil", "municipio", limit=50)
    assert ref.full_table_id == "basedosdados.br_bd_diretorios_brasil.municipio"
    assert ref.access == "free_logged_in"
    assert ref.sql == "SELECT * FROM `basedosdados.br_bd_diretorios_brasil.municipio` LIMIT 50"


@respx.mock
def test_direct_download_free_economics_search() -> None:
    clear_cache()
    respx.get("https://backend.basedosdados.org/search/").mock(
        return_value=httpx.Response(
            200,
            json={
                "page": 1,
                "page_size": 10,
                "count": 44,
                "results": [
                    {
                        "id": "544c9d22-97b7-479a-8eca-94762840b465",
                        "slug": "sicor",
                        "name": "Microdados do Sistema de Operações do Crédito Rural",
                        "contains_direct_download_free": True,
                        "contains_closed_data": False,
                    }
                ],
                "aggregations": {},
                "locale": "pt",
            },
        )
    )

    client = TestClient(app)
    r = client.get("/basedosdados/direct-download/free", params={"theme": "economics"})

    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 44
    assert body["results"][0]["slug"] == "sicor"

    request = respx.calls.last.request
    assert request.url.params["contains"] == "direct_download_free"
    assert request.url.params["theme"] == "economics"
    assert request.url.params["locale"] == "pt"


def test_sdk_endpoints_fail_clean_when_optional_package_absent(monkeypatch) -> None:
    clear_cache()
    monkeypatch.setattr(
        catalog,
        "_load_sdk",
        lambda: (_ for _ in ()).throw(
            catalog.BaseDosDadosSDKNotInstalledError("Install findata-br[basedosdados]")
        ),
    )
    client = TestClient(app)
    r = client.get("/basedosdados/datasets")
    assert r.status_code == 503
    assert "findata-br[basedosdados]" in r.json()["detail"]


def test_resolve_billing_project_prefers_explicit(monkeypatch) -> None:
    monkeypatch.setenv("FINDATA_BD_BILLING_PROJECT_ID", "env-project")
    assert catalog.resolve_billing_project_id("explicit-project") == "explicit-project"
    assert catalog.resolve_billing_project_id() == "env-project"


def test_read_sql_preview_calls_sdk_with_project_and_caps_rows(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeFrame:
        def __init__(self, rows: list[dict[str, object]]) -> None:
            self._rows = rows

        def head(self, n: int) -> FakeFrame:
            return FakeFrame(self._rows[:n])

        def to_dict(self, orient: str) -> list[dict[str, object]]:
            assert orient == "records"
            return self._rows

    class FakeSDK:
        @staticmethod
        def read_sql(**kwargs: object) -> FakeFrame:
            calls.update(kwargs)
            return FakeFrame([{"id": 1}, {"id": 2}, {"id": 3}])

    monkeypatch.setattr(catalog, "_load_sdk", lambda: FakeSDK)
    result = catalog.read_sql_preview(
        "SELECT 1",
        billing_project_id="billing-project",
        reauth=True,
        use_bqstorage_api=True,
        max_rows=2,
    )

    assert calls == {
        "query": "SELECT 1",
        "billing_project_id": "billing-project",
        "from_file": False,
        "reauth": True,
        "use_bqstorage_api": True,
    }
    assert result.row_count == 2
    assert result.rows == [{"id": 1}, {"id": 2}]
