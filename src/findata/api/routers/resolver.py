"""Asset-classification resolver routes.

Wraps :func:`findata.resolver.resolve_asset` over HTTP. The consolidator calls
this per asset (dozens per statement), so the handler is a thin, cacheable pass
through the deterministic core. No PII: only an asset identifier crosses the
boundary.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from findata.resolver import AssetClassification, resolve_asset

router = APIRouter(prefix="/resolver", tags=["Resolver"])


@router.get("/resolve")
async def resolve(
    name: str | None = Query(
        None, max_length=256, description="Nome/label do ativo (ex.: 'FI ITAUINFRA CI')"
    ),
    ticker: str | None = Query(None, max_length=16, description="Ticker B3 (ex.: IFRA11, PETR4)"),
    cnpj: str | None = Query(None, max_length=32, description="CNPJ do fundo (com ou sem máscara)"),
    isin: str | None = Query(None, max_length=16, description="ISIN (ex.: BR...)"),
) -> AssetClassification:
    """Classifica um ativo na taxonomia macro de alocação.

    Aceita qualquer identificador (``name``/``ticker``/``cnpj``/``isin``) e
    devolve ``macro_class`` (classe de ativo: Renda Fixa, Renda Variável,
    Multimercado, Alternativos, Estruturados) + ``exposure`` (eixo ortogonal de
    geografia: Brasil/Internacional) + subclasse, underlying, debênture/Lei
    12.431, ``source``, ``confidence``, ``signals`` e a cascata percorrida.
    Determinístico e cacheável.
    """
    return await resolve_asset(name=name, ticker=ticker, cnpj=cnpj, isin=isin)
