"""ANBIMA API routes — fully public, no credentials required.

Backed by ANBIMA's free static-file downloads (`www.anbima.com.br/informacoes/*`),
not the gated Sensedia API. Same canonical data, just delivered as files.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from findata.sources.anbima import indices as anbima

router = APIRouter(prefix="/anbima", tags=["ANBIMA"])


@router.get("/ima")
async def ima(
    family: anbima.IMAFamily | None = Query(default=None),
) -> list[anbima.IMADataPoint]:
    """Latest IMA snapshot — every family, every sub-index, last published day.

    ANBIMA's `ima_completo.xls` is a one-day snapshot, so this returns one
    row per sub-index (e.g. `IRF-M 1`, `IRF-M 1+`, `IRF-M` rolling total).
    Pass `family` to filter to one index. Cached for 24h.
    """
    return await anbima.get_ima(family)


@router.get("/ettj")
async def ettj(data: date | None = Query(default=None)) -> list[anbima.ETTJDataPoint]:
    """Yield curve (zero coupon) for a reference date."""
    return await anbima.get_ettj(data)


@router.get("/debentures")
async def debentures(
    data: date | None = Query(default=None),
    emissor: str | None = Query(default=None, description="Substring filter on issuer name"),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[anbima.DebentureQuote]:
    """Daily secondary-market quotes for outstanding debentures."""
    rows = await anbima.get_debentures(data, emissor=emissor)
    return rows[:limit]


@router.get("/tpf")
async def tpf(
    data: date | None = Query(default=None),
    titulo: str | None = Query(
        default=None, description="Filter by bond type, e.g. LTN, NTN-B, LFT"
    ),
    limit: int = Query(default=1000, ge=1, le=5000),
) -> list[anbima.TPFQuote]:
    """Daily secondary-market reference rates for federal government bonds (TPF)."""
    rows = await anbima.get_tpf(data)
    if titulo:
        needle = titulo.upper()
        rows = [r for r in rows if needle in r.titulo.upper()]
    return rows[:limit]
