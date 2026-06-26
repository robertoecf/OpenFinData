"""Curated MCP surface for the findata-br server.

The public REST API (``findata.api.app``) exposes ~95 fine-grained routes, one
per upstream dataset/endpoint. Mapping those 1:1 to MCP tools floods an agent's
context with ~95 near-duplicate tool schemas before it makes a single call, and
hurts tool-selection accuracy.

This module is a *separate* FastAPI app whose only purpose is to be the source
of the MCP tool catalog. It exposes a small, hand-curated set of tools, each
with an agent-oriented description, that dispatch to the same
``findata.sources.*`` functions the REST routers use. Consolidated tools collapse
sprawly clusters (e.g. the 12 BCB and 14 CVM-fund endpoints) behind a few
``dataset``/``kind`` selectors.

Wiring lives in ``app.py``: ``FastApiMCP(mcp_app).mount_http(router=app)`` builds
the tool catalog from *this* app while serving ``/mcp`` on the public app. The
95 REST routes are never touched.

  A, curation: only the headline tools are exposed, with real descriptions.
  B, consolidation: ``bcb_*``/``cvm_*``/``tesouro_*``… fold many routes into one.
  C, code mode: optional ``findata_run_code`` runs a Python snippet against the
      library (gated by ``FINDATA_MCP_CODE_MODE=1``; off by default).
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from findata.registry import lookup
from findata.sources.anbima import indices as anbima_src
from findata.sources.aneel import leiloes
from findata.sources.b3 import cotahist, indices
from findata.sources.basedosdados import catalog
from findata.sources.bcb import focus, ptax, sgs
from findata.sources.cvm import (
    companies,
    fca,
    fidc,
    fii,
    financials,
    fip,
    funds,
    holdings,
    ipe,
    lamina,
    list_periods,
    profile,
)
from findata.sources.ibge import indicators
from findata.sources.ipea import series as ipea_series
from findata.sources.openfinance import directory as of_dir
from findata.sources.receita import arrecadacao
from findata.sources.susep import empresas
from findata.sources.tesouro import bonds, siconfi

router = APIRouter()

_MAX_TICKERS = 20
_MIN_YEAR_BCB_SGS = 1986


# ── Registry: the entry point ─────────────────────────────────────


@router.get(
    "/registry/lookup",
    operation_id="registry_lookup",
    response_model=None,
    summary="Resolve a CNPJ, B3 ticker, CVM/SUSEP code, or company name to canonical entities",
)
async def registry_lookup(
    q: str = Query(
        ...,
        min_length=2,
        description="CNPJ (masked or not), ticker (PETR4), CVM/SUSEP code, or name fragment",
    ),
    limit: int = Query(20, ge=1, le=100),
) -> Any:
    """Offline cross-source resolver backed by an embedded FTS5 catalog.

    Start here to turn a fuzzy identifier into a CNPJ + tickers + source codes
    before calling the source-specific tools. The BM25 ``rank`` indicates match
    strength (very negative = strong exact hit; near zero = fuzzy name match).
    """
    return await lookup(q, limit=limit)


# ── BCB: Banco Central ────────────────────────────────────────────


@router.get(
    "/bcb/series",
    operation_id="bcb_series",
    response_model=None,
    summary="BCB time series (Selic, IPCA, câmbio…): list the catalog or fetch by code/name",
)
async def bcb_series(
    code: int | None = Query(None, description="SGS numeric code, e.g. 432=Selic meta, 433=IPCA"),
    name: str | None = Query(None, description="Catalog alias, e.g. selic, ipca, dolar_ptax"),
    start: date | None = Query(None, description="Start date YYYY-MM-DD (code mode only)"),
    end: date | None = Query(None, description="End date YYYY-MM-DD (code mode only)"),
    last_n: int | None = Query(None, ge=1, le=1000, description="Return only the last N values"),
) -> Any:
    """Three modes in one tool. Pass nothing to list the curated catalog; pass
    ``code`` for a series by SGS code (optionally ``start``/``end`` or ``last_n``);
    or pass ``name`` for the most recent values of a named series.
    """
    if code is not None:
        if last_n is not None:
            return await sgs.get_series_last(code, last_n)
        return await sgs.get_series(code, start, end)
    if name is not None:
        return await sgs.get_series_by_name(name, last_n or 10)
    return sgs.SERIES_CATALOG


@router.get(
    "/bcb/ptax",
    operation_id="bcb_ptax",
    response_model=None,
    summary="PTAX official exchange rate for any currency, single date or a date range",
)
async def bcb_ptax(
    currency: str = Query("USD", description="ISO currency code, e.g. USD, EUR, GBP"),
    date_: date | None = Query(None, alias="date", description="Single date (default: latest)"),
    start: date | None = Query(None, description="Range start (use with end; USD only)"),
    end: date | None = Query(None, description="Range end (use with start; USD only)"),
) -> Any:
    """Official PTAX from BCB. Pass ``start``+``end`` for a daily series over a
    range (USD only), or ``date`` (or nothing) for a single day. ``currency=USD``
    is the common case; other currencies support single-date queries only.
    """
    if start is not None and end is not None:
        if currency.upper() != "USD":
            raise HTTPException(400, "Range queries are USD-only; use `date` for other currencies")
        return await ptax.get_ptax_usd_period(start, end)
    if currency.upper() == "USD":
        return await ptax.get_ptax_usd(date_)
    return await ptax.get_ptax_currency(currency, date_)


@router.get(
    "/bcb/focus",
    operation_id="bcb_focus",
    response_model=None,
    summary="Boletim Focus expectations, annual/monthly, market or Top-5, or Selic per COPOM",
)
async def bcb_focus(
    indicator: str = Query(
        "IPCA",
        description="Indicator, e.g. IPCA, 'PIB Total', Câmbio. Use 'Selic' for COPOM path, "
        "'list' to see available indicators.",
    ),
    horizon: Literal["annual", "monthly"] = Query("annual"),
    panel: Literal["market", "top5"] = Query(
        "market", description="market = all forecasters; top5 = Top-5 ranked (annual only)"
    ),
    top: int = Query(20, ge=1, le=100, description="Max rows to return"),
) -> Any:
    """Consolidates the Focus endpoints. ``indicator='list'`` returns the available
    indicators; ``indicator='Selic'`` returns the Selic expectation per COPOM
    meeting (horizon/panel ignored). Otherwise pick ``horizon`` and ``panel``.
    """
    key = indicator.strip().lower()
    if key == "list":
        return focus.FOCUS_INDICATORS
    if key == "selic":
        return await focus.get_focus_selic(top)
    if panel == "top5":
        return await focus.get_focus_top5_annual(indicator, top)
    if horizon == "monthly":
        return await focus.get_focus_monthly(indicator, top)
    return await focus.get_focus_annual(indicator, top)


# ── CVM: companies & funds ────────────────────────────────────────


@router.get(
    "/cvm/company",
    operation_id="cvm_company",
    response_model=None,
    summary="CVM-listed companies: search/list, registration facts (FCA), and filings (IPE)",
)
async def cvm_company(
    dataset: Literal[
        "search", "list", "fca_general", "fca_securities", "fca_dri", "filings"
    ] = Query("search"),
    query: str | None = Query(None, min_length=2, description="Name search (dataset=search)"),
    cnpj: str | None = Query(
        None, description="Company CNPJ filter (recommended for fca_*/filings)"
    ),
    year: int | None = Query(
        None, ge=2003, description="Reference year (required for fca_*/filings)"
    ),
    ticker: str | None = Query(None, description="B3 ticker filter (dataset=fca_securities)"),
    categoria: str | None = Query(
        None, description="Filing category (dataset=filings), e.g. 'Fato Relevante'"
    ),
    limit: int = Query(100, ge=1, le=2000),
) -> Any:
    """The company side of CVM. ``search`` needs ``query``; ``list`` is the full
    registry. ``fca_general|fca_securities|fca_dri`` are cadastral facets needing
    ``year`` (+ optional ``cnpj``/``ticker``). ``filings`` (IPE, fatos relevantes,
    comunicados) needs ``year`` (+ optional ``cnpj``/``categoria``).
    """
    if dataset == "search":
        if not query:
            raise HTTPException(400, "dataset=search requires `query`")
        return (await companies.search_company(query, True))[:limit]
    if dataset == "list":
        return (await companies.get_companies(True))[:limit]
    if dataset == "filings":
        if year is None:
            raise HTTPException(400, "dataset=filings requires `year`")
        return (await ipe.get_ipe(year, cnpj=cnpj, categoria=categoria))[:limit]
    if year is None:
        raise HTTPException(400, f"dataset={dataset} requires `year`")
    if dataset == "fca_general":
        return await fca.get_fca_geral(year, cnpj)
    if dataset == "fca_securities":
        return await fca.get_fca_valores_mobiliarios(year, cnpj=cnpj, ticker=ticker)
    return await fca.get_fca_dri(year, cnpj)


@router.get(
    "/cvm/financials",
    operation_id="cvm_financials",
    response_model=None,
    summary="CVM financial statements, annual (DFP) or quarterly (ITR) for a company",
)
async def cvm_financials(
    year: int = Query(..., ge=2010, description="Fiscal year"),
    period: Literal["annual", "quarterly"] = Query(
        "annual", description="annual=DFP, quarterly=ITR"
    ),
    statement: financials.StatementType = Query(
        financials.StatementType.DRE_CON,
        description="Statement type: BPA/BPP/DRE/DFC_MI/DMPL/DVA, _con (consolidated) or _ind",
    ),
    cnpj: str | None = Query(
        None, description="Company CNPJ, strongly recommended (avoids the full dataset)"
    ),
    limit: int = Query(500, ge=1, le=5000),
) -> Any:
    """Annual DFP or quarterly ITR statements. Statement types: BPA_con, BPP_con,
    DRE_con, DFC_MI_con, DMPL_con, DVA_con (+ ``_ind`` variants). Always pass ``cnpj``.
    """
    if period == "quarterly":
        return (await financials.get_itr(year, statement, cnpj))[:limit]
    return (await financials.get_dfp(year, statement, cnpj))[:limit]


@router.get(
    "/cvm/fund",
    operation_id="cvm_fund",
    response_model=None,
    summary="Open-ended CVM funds (FI): catalog, daily NAV, holdings, factsheet, returns, profile",
)
async def cvm_fund(
    dataset: Literal[
        "catalog", "daily", "holdings", "lamina", "returns", "profile", "periods"
    ] = Query("catalog"),
    cnpj: str | None = Query(
        None, description="Fund CNPJ (required for holdings; recommended elsewhere)"
    ),
    year: int | None = Query(None, description="Reference year (required except catalog/periods)"),
    month: int | None = Query(None, ge=1, le=12, description="Reference month (monthly datasets)"),
    horizon: Literal["monthly", "yearly"] = Query(
        "monthly", description="returns granularity (dataset=returns)"
    ),
    blocks: str | None = Query(
        None,
        description="holdings: block whitelist, e.g. BLC_1,BLC_4 (of BLC_1..BLC_8,CONFID,PL,FIE)",
    ),
    product: str = Query(
        "INF_DIARIO",
        description="periods: INF_DIARIO|CDA|LAMINA|PERFIL_MENSAL|BALANCETE|EVENTUAL|EXTRATO",
    ),
    limit: int = Query(500, ge=1, le=5000),
) -> Any:
    """Open funds in one tool. ``catalog`` lists registered funds; ``periods`` lists
    the YYYYMM stamps available upstream for ``product``. The rest need ``year``;
    ``daily``/``holdings``/``lamina``/``returns``/``profile`` need ``month`` too, and
    ``holdings`` requires ``cnpj`` (the monthly CDA file is huge).
    """
    if dataset == "catalog":
        return (await funds.get_fund_catalog(True, None))[:limit]
    if dataset == "periods":
        return await list_periods("FI", f"DOC/{product}")
    if year is None:
        raise HTTPException(400, f"dataset={dataset} requires `year`")
    if dataset == "holdings":
        if not cnpj or month is None:
            raise HTTPException(400, "dataset=holdings requires `cnpj` and `month`")
        block_list = [b.strip() for b in blocks.split(",") if b.strip()] if blocks else None
        return await holdings.get_fund_holdings(cnpj, year, month, block_list)
    if month is None:
        raise HTTPException(400, f"dataset={dataset} requires `month`")
    if dataset == "daily":
        return (await funds.get_fund_daily(year, month, cnpj))[:limit]
    if dataset == "lamina":
        return (await lamina.get_fund_lamina(year, month, cnpj))[:limit]
    if dataset == "profile":
        return (await profile.get_fund_profile(year, month, cnpj))[:limit]
    if horizon == "yearly":
        return (await lamina.get_fund_yearly_returns(year, month, cnpj))[:limit]
    return (await lamina.get_fund_monthly_returns(year, month, cnpj))[:limit]


async def _structured_fii(
    dataset: str | None, cnpj: str | None, year: int, month: int | None
) -> Any:
    if dataset in (None, "geral"):
        return await fii.get_fii_geral(year, cnpj=cnpj, month=month)
    if dataset == "complemento":
        return await fii.get_fii_complemento(year, cnpj=cnpj, month=month)
    raise HTTPException(400, f"unknown FII dataset {dataset!r} (use geral|complemento)")


async def _structured_fidc(
    dataset: str | None, cnpj: str | None, year: int, month: int | None
) -> Any:
    if month is None:
        raise HTTPException(400, "FIDC datasets require `month`")
    if dataset in (None, "geral"):
        return await fidc.get_fidc_geral(year, month, cnpj=cnpj)
    if dataset == "pl":
        return await fidc.get_fidc_pl(year, month, cnpj=cnpj)
    if dataset in ("direitos", "direitos-creditorios"):
        return await fidc.get_fidc_direitos_creditorios(year, month, cnpj=cnpj)
    raise HTTPException(400, f"unknown FIDC dataset {dataset!r} (use geral|pl|direitos)")


@router.get(
    "/cvm/structured-fund",
    operation_id="cvm_structured_fund",
    response_model=None,
    summary="Structured CVM funds, FII (real estate), FIDC (receivables), FIP (private equity)",
)
async def cvm_structured_fund(
    kind: Literal["fii", "fidc", "fip"] = Query(...),
    dataset: str | None = Query(
        None, description="fii: geral|complemento; fidc: geral|pl|direitos; fip: (n/a)"
    ),
    cnpj: str | None = Query(None, description="Fund CNPJ filter"),
    year: int = Query(..., description="Reference year"),
    month: int | None = Query(None, ge=1, le=12, description="Required for FIDC; optional for FII"),
    quarter: int | None = Query(None, ge=1, le=4, description="FIP only, informe quarter"),
    limit: int = Query(500, ge=1, le=5000),
) -> Any:
    """Structured funds by ``kind``. FII has ``geral`` (cadastral) and ``complemento``
    (cotistas/PL/taxa) facets. FIDC has ``geral``/``pl``/``direitos`` (needs ``month``).
    FIP returns the quarterly informe (optional ``quarter``).
    """
    if kind == "fii":
        return await _structured_fii(dataset, cnpj, year, month)
    if kind == "fidc":
        return await _structured_fidc(dataset, cnpj, year, month)
    return (await fip.get_fip(year, cnpj=cnpj, quarter=quarter))[:limit]


# ── B3: Bolsa ─────────────────────────────────────────────────────


def _b3_quotes() -> Any:
    try:
        from findata.sources.b3 import quotes
    except ImportError as exc:  # pragma: no cover, only without the [b3] extra
        raise HTTPException(
            503, "Live quotes need the optional extra: pip install 'openfindata[b3]'"
        ) from exc
    return quotes


@router.get(
    "/b3/quote",
    operation_id="b3_quote",
    response_model=None,
    summary="Live B3 stock quote(s) (optional [b3] extra), prefer b3_cotahist for official EOD",
)
async def b3_quote(
    tickers: str = Query(
        ..., description="One ticker or comma-separated list (max 20), e.g. PETR4,VALE3"
    ),
) -> Any:
    """Current quote(s) from the optional yfinance-backed source. For canonical,
    official end-of-day history use ``b3_cotahist`` instead.
    """
    quotes = _b3_quotes()
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(400, "at least one ticker is required")
    if len(ticker_list) > _MAX_TICKERS:
        raise HTTPException(400, f"max {_MAX_TICKERS} tickers per request")
    if len(ticker_list) == 1:
        return await quotes.get_quote(ticker_list[0])
    return await quotes.get_multiple_quotes(ticker_list)


@router.get(
    "/b3/cotahist",
    operation_id="b3_cotahist",
    response_model=None,
    summary="Official B3 COTAHIST daily quotes, by year, month, or single day",
)
async def b3_cotahist(
    year: int = Query(..., ge=_MIN_YEAR_BCB_SGS, description="Year (B3 publishes since 1986)"),
    month: int | None = Query(None, ge=1, le=12),
    day: int | None = Query(None, ge=1, le=31),
    ticker: str | None = Query(
        None, description="CODNEG filter, e.g. PETR4, recommended (annual files are ~85 MB)"
    ),
    market_codes: str | None = Query(
        None, description="CODBDI whitelist, comma-separated, e.g. 02,96"
    ),
) -> Any:
    """Granularity follows the args: ``day`` (needs ``month``) → one trading day,
    ``month`` → one month, otherwise the whole ``year``. Pass ``ticker`` for
    single-issuer queries.
    """
    codes = [c.strip() for c in market_codes.split(",") if c.strip()] if market_codes else None
    if day is not None:
        if month is None:
            raise HTTPException(400, "`day` requires `month`")
        return await cotahist.get_cotahist_day(year, month, day, ticker, codes)
    if month is not None:
        return await cotahist.get_cotahist_month(year, month, ticker, codes)
    return await cotahist.get_cotahist_year(year, ticker, codes)


@router.get(
    "/b3/index",
    operation_id="b3_index",
    response_model=None,
    summary="B3 index theoretical portfolio & monthly history (IBOV, IBrX, SMLL, IDIV, IFIX…)",
)
async def b3_index(
    symbol: str | None = Query(
        None, description="Index symbol, e.g. IBOV; omit to list known indices"
    ),
    dataset: Literal["portfolio", "monthly"] = Query(
        "portfolio", description="portfolio=current composição; monthly=closing levels"
    ),
    start: date | None = Query(None, description="monthly: start date YYYY-MM-DD"),
    end: date | None = Query(None, description="monthly: end date YYYY-MM-DD"),
    months: int = Query(120, ge=1, le=360, description="monthly window when start omitted"),
) -> Any:
    """Omit ``symbol`` to list the indices we can fetch. With ``symbol``,
    ``portfolio`` returns the current composição (constituents + weights);
    ``monthly`` returns closing levels for charting.
    """
    if symbol is None:
        return await indices.list_known_indices()
    if dataset == "monthly":
        return await indices.get_index_monthly_evolution(
            symbol, start=start, end=end, months=months
        )
    return await indices.get_index_portfolio(symbol)


# ── Tesouro / SICONFI ──────────────────────────────────────────────


@router.get(
    "/tesouro/bonds",
    operation_id="tesouro_bonds",
    response_model=None,
    summary="Tesouro Direto bonds, list/filter, search names, or price+rate history",
)
async def tesouro_bonds(
    dataset: Literal["list", "search", "history"] = Query("list"),
    titulo: str | None = Query(
        None, description="Bond name for history, e.g. 'Tesouro IPCA+ 2035'"
    ),
    q: str | None = Query(None, min_length=2, description="Search query (dataset=search)"),
    tipo: str | None = Query(None, description="Type filter (dataset=list), e.g. 'Tesouro IPCA+'"),
    start: date | None = Query(None),
    end: date | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
) -> Any:
    """``list`` returns current bond prices/rates (filter by ``tipo``/date);
    ``search`` finds bond names from ``q``; ``history`` returns the series for a
    single ``titulo``.
    """
    if dataset == "search":
        if not q:
            raise HTTPException(400, "dataset=search requires `q`")
        return await bonds.search_bonds(q)
    if dataset == "history":
        if not titulo:
            raise HTTPException(400, "dataset=history requires `titulo`")
        return await bonds.get_bond_history(titulo, start, end)
    return await bonds.get_treasury_bonds(tipo, start, end, limit)


@router.get(
    "/tesouro/siconfi",
    operation_id="tesouro_siconfi",
    response_model=None,
    summary="SICONFI public-finance reports, RREO, RGF, or the federation-entity list",
)
async def tesouro_siconfi(
    report: Literal["rreo", "rgf", "entes"] = Query("entes"),
    year: int | None = Query(None, ge=2013),
    period: int | None = Query(
        None, ge=1, le=6, description="RREO: bimestre 1-6; RGF: quadrimestre 1-3"
    ),
    cod_ibge: int | None = Query(
        None, description="IBGE entity code (1=União); discover via report=entes"
    ),
    poder: str = Query("E", description="RGF only: E/L/J/M/D power branch"),
    anexo: str | None = Query(None, description='e.g. "RREO-Anexo 01"'),
) -> Any:
    """``entes`` lists every federation entity with its IBGE code (start here).
    ``rreo`` (bimestral) and ``rgf`` (quadrimestral) need ``year``, ``period``, and
    ``cod_ibge``.
    """
    if report == "entes":
        return await siconfi.get_entes()
    if year is None or period is None or cod_ibge is None:
        raise HTTPException(400, f"report={report} requires year, period, and cod_ibge")
    if report == "rgf":
        return await siconfi.get_rgf(year, period, cod_ibge, poder=poder)  # type: ignore[arg-type]
    return await siconfi.get_rreo(year, period, cod_ibge, anexo=anexo)


# ── IBGE ───────────────────────────────────────────────────────────


@router.get(
    "/ibge/indicator",
    operation_id="ibge_indicator",
    response_model=None,
    summary="IBGE economic indicators, list the catalog or fetch one by name (e.g. ipca_mensal)",
)
async def ibge_indicator(
    name: str | None = Query(None, description="Indicator name; omit to list all available"),
    periods: int = Query(12, ge=1, le=120, description="Recent periods to return"),
) -> Any:
    """Omit ``name`` to list every IBGE indicator we expose; pass ``name`` to fetch
    its recent values.
    """
    if name is None:
        return indicators.IBGE_INDICATORS
    return await indicators.get_indicator(name, periods)


@router.get(
    "/ibge/ipca-breakdown",
    operation_id="ibge_ipca_breakdown",
    response_model=None,
    summary="IPCA monthly variation broken down by the major groups (not available from BCB SGS)",
)
async def ibge_ipca_breakdown(
    periods: int = Query(6, ge=1, le=60, description="Recent months to return"),
) -> Any:
    """IPCA monthly variation for all major groups (food, housing, transport,
    health, …), granularity BCB SGS does not provide.
    """
    return await indicators.get_ipca_breakdown(periods)


# ── IPEA ───────────────────────────────────────────────────────────


@router.get(
    "/ipea/series",
    operation_id="ipea_series",
    response_model=None,
    summary="IPEA series, curated catalog, series values, or metadata by SERCODIGO",
)
async def ipea_series_tool(
    sercodigo: str | None = Query(
        None, description="Series code, e.g. BM12_TJOVER12; omit to list the curated catalog"
    ),
    dataset: Literal["values", "metadata"] = Query("values"),
    top: int | None = Query(None, ge=1, le=5000, description="Most recent N values"),
) -> Any:
    """Omit ``sercodigo`` to list the curated catalog. With it, ``values`` returns
    the observations and ``metadata`` returns name/unit/periodicity/source. For
    discovery across the full ~8k-series catalog use ``ipea_search``.
    """
    if sercodigo is None:
        return ipea_series.IPEA_CATALOG
    if dataset == "metadata":
        meta = await ipea_series.get_metadata(sercodigo)
        if meta is None:
            raise HTTPException(404, f"unknown SERCODIGO: {sercodigo}")
        return meta
    return await ipea_series.get_series_values(sercodigo, top)


@router.get(
    "/ipea/search",
    operation_id="ipea_search",
    response_model=None,
    summary="Full-text search across the ~8k-series IPEA catalog",
)
async def ipea_search(
    q: str = Query(..., min_length=2, description="Search query"),
    top: int = Query(25, ge=1, le=200),
) -> Any:
    """Find IPEA series by free-text query; returns metadata you can feed back to
    ``ipea_series`` as ``sercodigo``.
    """
    return await ipea_series.search_series(q, top)


# ── ANBIMA ─────────────────────────────────────────────────────────


@router.get(
    "/anbima",
    operation_id="anbima",
    response_model=None,
    summary="ANBIMA public data, IMA index family, ETTJ yield curve, or debenture quotes",
)
async def anbima_tool(
    dataset: Literal["ima", "ettj", "debentures"] = Query("ima"),
    family: str | None = Query(
        None, description="ima: filter to one IMA family, e.g. IRF-M, IMA-B"
    ),
    data: date | None = Query(None, description="Reference date (ettj/debentures; default latest)"),
    emissor: str | None = Query(None, description="debentures: issuer-name substring filter"),
    limit: int = Query(500, ge=1, le=5000),
) -> Any:
    """``ima`` returns the latest IMA snapshot (optionally one ``family``); ``ettj``
    returns the zero-coupon yield curve for ``data``; ``debentures`` returns daily
    secondary-market quotes (optionally filtered by ``emissor``).
    """
    if dataset == "ettj":
        return await anbima_src.get_ettj(data)
    if dataset == "debentures":
        rows = await anbima_src.get_debentures(data)
        if emissor:
            needle = emissor.upper()
            rows = [r for r in rows if needle in r.emissor.upper()]
        return rows[:limit]
    fam = anbima_src.IMAFamily(family) if family else None
    return (await anbima_src.get_ima(fam))[:limit]


# ── Open Finance Brasil ────────────────────────────────────────────


@router.get(
    "/openfinance/directory",
    operation_id="openfinance_directory",
    response_model=None,
    summary="Open Finance Brasil Directory, participants, API endpoints, resources, or roles",
)
async def openfinance_directory(
    dataset: Literal["participants", "endpoints", "resources", "roles"] = Query("participants"),
    role: str | None = Query(None, description="participants: Directory role filter, e.g. DADOS"),
    status: str | None = Query(
        "Active", description="participants/endpoints: status; empty for all"
    ),
    api_family: str | None = Query(
        None, description="participants/endpoints: API family substring"
    ),
    q: str | None = Query(None, min_length=2, description="participants: name/CNPJ substring"),
    limit: int = Query(100, ge=1, le=1000),
) -> Any:
    """``participants`` lists ecosystem participants (summarised); ``endpoints``
    flattens their advertised API endpoints; ``resources`` lists supported public
    resources; ``roles`` lists Directory roles.
    """
    env: of_dir.Environment = "production"
    if dataset == "resources":
        return of_dir.public_resources(env)
    if dataset == "roles":
        return (await of_dir.get_roles(env))[:limit]
    raw = await of_dir.get_participants(env)
    if dataset == "endpoints":
        return of_dir.flatten_api_endpoints(raw, api_family=api_family, status=status or None)[
            :limit
        ]
    filtered = of_dir.filter_participants(
        raw, role=role, status=status or None, api_family=api_family, query=q
    )
    return of_dir.summarise_participants(filtered[:limit])


# ── Base dos Dados ─────────────────────────────────────────────────


@router.get(
    "/basedosdados/search",
    operation_id="basedosdados_search",
    response_model=None,
    summary="Search the Base dos Dados catalog (free BigQuery datasets)",
)
async def basedosdados_search(
    q: str | None = Query(None, min_length=2, description="Free-text query"),
    theme: str | None = Query(None, description="Theme filter, e.g. economics"),
    only_free_download: bool = Query(
        False, description="Restrict to datasets marked free direct-download"
    ),
    page: int = Query(1, ge=1),
) -> Any:
    """Search the public catalog. Set ``only_free_download=true`` to restrict to
    datasets you can download without BigQuery. Use ``basedosdados_sql`` to get a
    starter query for a chosen table.
    """
    if only_free_download:
        return await catalog.search_direct_download_free(theme=theme, page=page)
    return await catalog.search_datasets(q=q, theme=theme, page=page)


@router.get(
    "/basedosdados/sql",
    operation_id="basedosdados_sql",
    response_model=None,
    summary="Generate a starter BigQuery SQL snippet for a Base dos Dados table",
)
async def basedosdados_sql(
    dataset_id: str = Query(..., min_length=1),
    table_id: str = Query(..., min_length=1),
    limit: int = Query(100, ge=1, le=10_000),
) -> Any:
    """Returns a ready-to-run BigQuery reference (project.dataset.table + a LIMITed
    SELECT) for the given Base dos Dados table.
    """
    return catalog.table_ref(dataset_id, table_id, limit)


# ── Receita Federal ────────────────────────────────────────────────


@router.get(
    "/receita/arrecadacao",
    operation_id="receita_arrecadacao",
    response_model=None,
    summary="Receita Federal monthly tax revenue (arrecadação) by period, UF, and tributo",
)
async def receita_arrecadacao(
    year: int | None = Query(None, ge=2000),
    month: int | None = Query(None, ge=1, le=12),
    uf: str | None = Query(None, description="State UF, e.g. SP, RJ"),
    tributo: str | None = Query(None, description="Tax-category substring, e.g. IRPF, COFINS"),
    limit: int = Query(500, ge=1, le=5000),
) -> Any:
    """Federal-tax revenue in long form (one row per period × UF × tributo).
    Filter by any combination of ``year``/``month``/``uf``/``tributo``.
    """
    rows = await arrecadacao.get_arrecadacao(year, month, uf, tributo)
    return rows[:limit]


# ── ANEEL ──────────────────────────────────────────────────────────


@router.get(
    "/aneel/leiloes",
    operation_id="aneel_leiloes",
    response_model=None,
    summary="ANEEL energy-auction results, generation or transmission",
)
async def aneel_leiloes(
    kind: Literal["geracao", "transmissao"] = Query("geracao"),
    year: int | None = Query(None),
    fonte: str | None = Query(
        None, description="geracao: energy-source substring, e.g. Eólica, Solar"
    ),
    uf: str | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
) -> Any:
    """Winning bids per auction. ``geracao`` (since 2005) supports a ``fonte`` filter;
    ``transmissao`` (since 1999) does not. Both support ``year``/``uf``.
    """
    if kind == "transmissao":
        return (await leiloes.get_aneel_leiloes_transmissao(year=year, uf=uf))[:limit]
    return (await leiloes.get_aneel_leiloes_geracao(year=year, fonte=fonte, uf=uf))[:limit]


# ── SUSEP ──────────────────────────────────────────────────────────


@router.get(
    "/susep/empresas",
    operation_id="susep_empresas",
    response_model=None,
    summary="SUSEP-supervised entities (insurance, previdência, capitalização), list or search",
)
async def susep_empresas(
    q: str | None = Query(None, min_length=2, description="Name substring; omit to list all"),
    limit: int = Query(500, ge=1, le=5000),
) -> Any:
    """Pass ``q`` to search SUSEP entities by name; omit it to list all (paginated)."""
    if q:
        return await empresas.search_susep_empresa(q)
    return (await empresas.get_susep_empresas())[:limit]


# ── C: Code mode (optional, gated) ────────────────────────────────

_CODE_MODE_ENABLED = os.getenv("FINDATA_MCP_CODE_MODE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_CODE_OUTPUT_CAP = 20_000
_CODE_TIMEOUT_MAX = 120


class RunCodeRequest(BaseModel):
    """Input for the code-mode tool."""

    code: str = Field(
        ...,
        description="Python source to execute. The `findata` library is importable. "
        "Source functions are async, wrap calls in asyncio.run(). Print results to stdout.",
    )
    timeout_s: int = Field(
        30, ge=1, le=_CODE_TIMEOUT_MAX, description="Wall-clock timeout in seconds"
    )


async def _execute_code(code: str, timeout_s: int) -> dict[str, Any]:
    """Run ``code`` in an isolated child interpreter, capturing combined output.

    PROTOTYPE, this is NOT a security sandbox: the child runs arbitrary Python
    with full library and network access. It is gated off by default and intended
    for trusted, local/agent use only.
    """
    timeout = max(1, min(timeout_s, _CODE_TIMEOUT_MAX))
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",  # isolated mode: ignore env vars and user site, don't add cwd to path
        "-c",
        code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=tempfile.gettempdir(),
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return {"timed_out": True, "exit_code": None, "output": f"(killed: exceeded {timeout}s)"}
    text = stdout.decode("utf-8", errors="replace")
    return {
        "timed_out": False,
        "exit_code": proc.returncode,
        "truncated": len(text) > _CODE_OUTPUT_CAP,
        "output": text[:_CODE_OUTPUT_CAP],
    }


if _CODE_MODE_ENABLED:

    @router.post(
        "/run-code",
        operation_id="findata_run_code",
        response_model=None,
        summary="Run a Python snippet against the findata library and return its stdout",
    )
    async def findata_run_code(payload: RunCodeRequest) -> Any:
        """Execute arbitrary Python with the ``findata`` library available, returning
        captured stdout/stderr. This replaces dozens of fine-grained calls: filter,
        join, and aggregate across sources in one round-trip instead of streaming
        every intermediate result through the model's context.

        Example::

            import asyncio
            from findata.sources.bcb import ptax

            print(asyncio.run(ptax.get_ptax_usd()))

        Security: runs in an isolated child interpreter with a timeout and output
        cap, but is NOT a hardened sandbox. Enabled only when the server sets
        FINDATA_MCP_CODE_MODE=1.
        """
        return await _execute_code(payload.code, payload.timeout_s)


# ── The MCP-only FastAPI app ───────────────────────────────────────

mcp_app = FastAPI(
    title="findata-br (MCP)",
    description="Curated MCP tool surface for findata-br.",
    version="1",
)


@mcp_app.exception_handler(ValueError)
async def _value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


mcp_app.include_router(router)
