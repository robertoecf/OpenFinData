"""B3 API routes — Stock quotes, COTAHIST history, and index portfolios.

``yfinance`` is imported lazily (only on /b3/quote* paths) so the rest
of the API stays available even when the optional ``[b3]`` extra is not
installed. COTAHIST and indices use only core deps (httpx + stdlib).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query

from findata.sources.b3 import cotahist, indices

router = APIRouter(prefix="/b3", tags=["B3 - Bolsa"])

_MAX_TICKERS_PER_REQUEST = 20
_CURRENT_YEAR = date.today().year


def _quotes() -> Any:
    try:
        from findata.sources.b3 import quotes
    except ImportError as exc:  # pragma: no cover — triggered only without yfinance
        raise HTTPException(
            status_code=503,
            detail=(
                "B3 support is disabled. Install with: "
                "pip install 'findata-br[b3]'"
            ),
        ) from exc
    return quotes


@router.get("/quote/{ticker}")
async def get_quote(ticker: str) -> Any:
    """Get current stock quote for a B3 ticker (e.g., PETR4, VALE3, WEGE3)."""
    quotes = _quotes()
    try:
        return await quotes.get_quote(ticker)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Ticker not found: {ticker}") from exc


@router.get("/history/{ticker}")
async def get_history(
    ticker: str,
    period: str = Query(
        default="1mo",
        description="Period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max",
    ),
    interval: str = Query(
        default="1d",
        description="Interval: 1d, 1wk, 1mo",
    ),
) -> Any:
    """Get historical price data for a B3 stock."""
    quotes = _quotes()
    try:
        return await quotes.get_history(ticker, period, interval)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"No history for: {ticker}") from exc


@router.get("/quotes")
async def get_multiple_quotes(
    tickers: str = Query(..., description="Comma-separated tickers (e.g., PETR4,VALE3,ITUB4)"),
) -> Any:
    """Get current quotes for multiple B3 tickers."""
    quotes = _quotes()
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="At least one ticker is required")
    if len(ticker_list) > _MAX_TICKERS_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Max {_MAX_TICKERS_PER_REQUEST} tickers per request",
        )
    try:
        return await quotes.get_multiple_quotes(ticker_list)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── COTAHIST — Official daily-quotes time series ─────────────────


@router.get("/cotahist/year/{year}")
async def cotahist_year(
    year: int,
    ticker: str | None = Query(default=None, description="CODNEG filter (recommended)"),
    market_codes: str | None = Query(
        default=None,
        description="Comma-separated CODBDI whitelist (02=lote padrão, 96=fracionário…)",
    ),
) -> list[cotahist.CotahistTrade]:
    """Read every COTAHIST record for a year (B3 publishes since 1986).

    Annual files are large (~85 MB unzipped). Pass ``ticker=PETR4`` for
    single-issuer queries.
    """
    codes = [c.strip() for c in market_codes.split(",")] if market_codes else None
    return await cotahist.get_cotahist_year(year, ticker, codes)


@router.get("/cotahist/month/{year}/{month}")
async def cotahist_month(
    year: int,
    month: int = Path(..., ge=1, le=12),
    ticker: str | None = Query(default=None),
    market_codes: str | None = Query(default=None),
) -> list[cotahist.CotahistTrade]:
    """Read one month of COTAHIST records (faster than annual)."""
    codes = [c.strip() for c in market_codes.split(",")] if market_codes else None
    return await cotahist.get_cotahist_month(year, month, ticker, codes)


@router.get("/cotahist/day/{year}/{month}/{day}")
async def cotahist_day(
    year: int,
    month: int = Path(..., ge=1, le=12),
    day: int = Path(..., ge=1, le=31),
    ticker: str | None = Query(default=None),
    market_codes: str | None = Query(default=None),
) -> list[cotahist.CotahistTrade]:
    """Read a single trading day of COTAHIST records."""
    codes = [c.strip() for c in market_codes.split(",")] if market_codes else None
    return await cotahist.get_cotahist_day(year, month, day, ticker, codes)


# ── Indices — Composição teórica (IBOV, IBrX, SMLL, IDIV, IFIX…) ──


@router.get("/indices")
async def list_indices() -> dict[str, str]:
    """List the B3 indices we know how to fetch (symbol → friendly name)."""
    return await indices.list_known_indices()


@router.get("/indices/{symbol}")
async def index_portfolio(symbol: str) -> indices.IndexPortfolio:
    """Current theoretical portfolio (composição) of a B3 index.

    Returns every constituent with weight (%), share class, and theoretical
    quantity. Refreshed quarterly by B3.
    """
    return await indices.get_index_portfolio(symbol)
