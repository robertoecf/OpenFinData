"""Base dos Dados integration.

Base dos Dados is a free source, but SQL/Python/R access commonly requires the
operator's own Google/BigQuery login and billing project. That makes it
``free_logged_in`` rather than a commercial-entitlement source like ANBIMA's
authenticated developer APIs.
"""

from __future__ import annotations

import importlib
import os
import re
from collections.abc import Callable
from typing import Any, cast

from findata.http_client import get_json
from findata.sources.basedosdados.models import (
    AccessPath,
    BaseDosDadosInfo,
    BigQueryTableRef,
    QueryPreview,
)

HOMEPAGE = "https://basedosdados.org/"
DOCS_URL = "https://basedosdados.org/docs/home"
PYTHON_DOCS_URL = "https://basedosdados.org/docs/api_reference_python"
BACKEND_SEARCH_URL = "https://backend.basedosdados.org/search/"
BILLING_PROJECT_ENV_VARS = (
    "FINDATA_BD_BILLING_PROJECT_ID",
    "BASE_DOS_DADOS_BILLING_PROJECT_ID",
    "GOOGLE_CLOUD_PROJECT",
)
_BQ_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


class BaseDosDadosSDKNotInstalledError(RuntimeError):
    """Raised when optional basedosdados SDK helpers are requested but absent."""


SOURCE_INFO = BaseDosDadosInfo(
    source="Base dos Dados",
    status="free_logged_in",
    homepage=HOMEPAGE,
    docs=DOCS_URL,
    access_paths=[
        AccessPath(
            name="Catalog/site/direct download",
            access="free_public",
            description="Public catalog metadata and direct downloads for eligible tables.",
        ),
        AccessPath(
            name="SQL via BigQuery",
            access="free_logged_in",
            description=(
                "Free access path, subject to Google BigQuery quota and user project setup."
            ),
            requires=["Google login", "Google Cloud/BigQuery project"],
        ),
        AccessPath(
            name="Python SDK",
            access="free_logged_in",
            description="Free Python access through the optional basedosdados SDK.",
            requires=["pip install findata-br[basedosdados]", "Google/BigQuery auth for queries"],
        ),
        AccessPath(
            name="R package",
            access="free_logged_in",
            description="Free R access through Base dos Dados' R package.",
            requires=["Google/BigQuery auth for queries"],
        ),
        AccessPath(
            name="BD Pro",
            access="paid_logged_in",
            description="Subscription-only datasets/features; not part of findata-br's free core.",
            requires=["Base dos Dados paid subscription"],
        ),
    ],
    notes=[
        (
            "Different from ANBIMA's authenticated developer products: "
            "the free SQL/Python/R paths are self-serve, but logged-in."
        ),
        "findata-br never ships user Google credentials or Base dos Dados paid entitlements.",
    ],
)


def resolve_billing_project_id(explicit: str | None = None) -> str | None:
    """Resolve BigQuery billing project from explicit value or common env vars."""
    if explicit:
        return explicit
    for name in BILLING_PROJECT_ENV_VARS:
        value = os.getenv(name)
        if value:
            return value
    return None


def _load_sdk() -> Any:
    try:
        return importlib.import_module("basedosdados")
    except ModuleNotFoundError as exc:
        raise BaseDosDadosSDKNotInstalledError(
            "Install the optional SDK with: pip install 'findata-br[basedosdados]'"
        ) from exc


def source_info() -> BaseDosDadosInfo:
    """Return access classification and docs links for Base dos Dados."""
    return SOURCE_INFO


def table_ref(dataset_id: str, table_id: str, limit: int = 100) -> BigQueryTableRef:
    """Build a BigQuery table reference and safe starter SQL."""
    dataset = dataset_id.strip()
    table = table_id.strip()
    if not _BQ_IDENTIFIER_RE.fullmatch(dataset) or not _BQ_IDENTIFIER_RE.fullmatch(table):
        raise ValueError("dataset_id and table_id must contain only letters, numbers and _")
    full = f"basedosdados.{dataset}.{table}"
    sql_limit = max(1, min(limit, 10_000))
    return BigQueryTableRef(
        dataset_id=dataset,
        table_id=table,
        full_table_id=full,
        sql=f"SELECT * FROM `{full}` LIMIT {sql_limit}",  # noqa: S608 - validated BQ ids
    )


async def search_datasets(
    q: str | None = None,
    contains: str | None = None,
    theme: str | None = None,
    page: int = 1,
    locale: str = "pt",
) -> dict[str, Any]:
    """Search Base dos Dados public catalog through the website backend.

    Useful filters from the public UI include ``contains=direct_download_free``
    and themes such as ``theme=economics``.
    """
    params: dict[str, Any] = {"page": page, "locale": locale}
    if q:
        params["q"] = q
    if contains:
        params["contains"] = contains
    if theme:
        params["theme"] = theme
    raw = await get_json(BACKEND_SEARCH_URL, params=params, cache_ttl=3600)
    return cast(dict[str, Any], raw)


async def search_direct_download_free(
    theme: str | None = None,
    page: int = 1,
    locale: str = "pt",
) -> dict[str, Any]:
    """Search datasets marked by Base dos Dados as free direct download."""
    return await search_datasets(
        contains="direct_download_free",
        theme=theme,
        page=page,
        locale=locale,
    )


def get_datasets(
    dataset_id: str | None = None,
    dataset_name: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> Any:
    """List Base dos Dados datasets through the optional basedosdados SDK."""
    sdk = _load_sdk()
    fn = cast(Callable[..., Any], sdk.get_datasets)
    return fn(dataset_id=dataset_id, dataset_name=dataset_name, page=page, page_size=page_size)


def get_tables(
    dataset_id: str | None = None,
    table_id: str | None = None,
    table_name: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> Any:
    """List Base dos Dados tables through the optional basedosdados SDK."""
    sdk = _load_sdk()
    fn = cast(Callable[..., Any], sdk.get_tables)
    return fn(
        dataset_id=dataset_id,
        table_id=table_id,
        table_name=table_name,
        page=page,
        page_size=page_size,
    )


def get_columns(
    table_id: str | None = None,
    column_id: str | None = None,
    columns_name: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> Any:
    """List Base dos Dados columns through the optional basedosdados SDK."""
    sdk = _load_sdk()
    fn = cast(Callable[..., Any], sdk.get_columns)
    return fn(
        table_id=table_id,
        column_id=column_id,
        columns_name=columns_name,
        page=page,
        page_size=page_size,
    )


def read_sql_preview(
    query: str,
    billing_project_id: str | None = None,
    from_file: bool = False,
    reauth: bool = False,
    use_bqstorage_api: bool = False,
    max_rows: int | None = None,
) -> QueryPreview:
    """Run a local, user-authenticated Base dos Dados SQL query.

    This is intentionally a library/CLI helper, not a public REST endpoint: the
    credentials and BigQuery billing project must belong to the local operator.
    """
    sdk = _load_sdk()
    fn = cast(Callable[..., Any], sdk.read_sql)
    resolved_project = resolve_billing_project_id(billing_project_id)
    df = fn(
        query=query,
        billing_project_id=resolved_project,
        from_file=from_file,
        reauth=reauth,
        use_bqstorage_api=use_bqstorage_api,
    )
    if max_rows is not None:
        df = df.head(max_rows)
    records = cast(list[dict[str, Any]], df.to_dict(orient="records"))
    return QueryPreview(query=query, rows=records, row_count=len(records))
