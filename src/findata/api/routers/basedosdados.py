"""Base dos Dados API routes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, HTTPException, Query

from findata.sources.basedosdados import catalog
from findata.sources.basedosdados.models import BaseDosDadosInfo, BigQueryTableRef

router = APIRouter(prefix="/basedosdados", tags=["Base dos Dados"])

_T = TypeVar("_T")


async def _sdk_call(fn: Callable[..., _T], **kwargs: object) -> _T:
    try:
        return await asyncio.to_thread(fn, **kwargs)
    except catalog.BaseDosDadosSDKNotInstalledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/info")
async def info() -> BaseDosDadosInfo:
    """Describe Base dos Dados access modes: free, free logged-in, and paid."""
    return catalog.source_info()


@router.get("/sql-template")
async def sql_template(
    dataset_id: str = Query(..., min_length=1),
    table_id: str = Query(..., min_length=1),
    limit: int = Query(default=100, ge=1, le=10_000),
) -> BigQueryTableRef:
    """Return a starter BigQuery SQL snippet for a Base dos Dados table."""
    return catalog.table_ref(dataset_id, table_id, limit)


@router.get("/search")
async def search(
    q: str | None = Query(default=None, min_length=2),
    contains: str | None = Query(default=None),
    theme: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    locale: str = Query(default="pt", min_length=2, max_length=5),
) -> dict[str, object]:
    """Search the public Base dos Dados catalog backend.

    Example: contains=direct_download_free&theme=economics.
    """
    return await catalog.search_datasets(
        q=q, contains=contains, theme=theme, page=page, locale=locale
    )


@router.get("/direct-download/free")
async def direct_download_free(
    theme: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    locale: str = Query(default="pt", min_length=2, max_length=5),
) -> dict[str, object]:
    """List datasets marked by Base dos Dados as free direct download."""
    return await catalog.search_direct_download_free(theme=theme, page=page, locale=locale)


@router.get("/datasets")
async def datasets(
    dataset_id: str | None = None,
    dataset_name: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> object:
    """List datasets via the optional basedosdados SDK."""
    return await _sdk_call(
        catalog.get_datasets,
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        page=page,
        page_size=page_size,
    )


@router.get("/tables")
async def tables(
    dataset_id: str | None = None,
    table_id: str | None = None,
    table_name: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> object:
    """List tables via the optional basedosdados SDK."""
    return await _sdk_call(
        catalog.get_tables,
        dataset_id=dataset_id,
        table_id=table_id,
        table_name=table_name,
        page=page,
        page_size=page_size,
    )


@router.get("/columns")
async def columns(
    table_id: str | None = None,
    column_id: str | None = None,
    columns_name: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> object:
    """List table columns via the optional basedosdados SDK."""
    return await _sdk_call(
        catalog.get_columns,
        table_id=table_id,
        column_id=column_id,
        columns_name=columns_name,
        page=page,
        page_size=page_size,
    )
