"""Yahoo Finance API routes — experimental and unofficial."""

from __future__ import annotations

from fastapi import APIRouter, Query

from findata.sources.yahoo import chart

router = APIRouter(prefix="/yahoo", tags=["Yahoo Finance - Experimental"])


@router.get("/chart/{symbol}")
async def yahoo_chart(
    symbol: str,
    range_: str = Query(default="1mo", alias="range"),
    interval: str = Query(default="1d"),
    include_pre_post: bool = Query(default=False),
) -> chart.YahooChart:
    """Experimental Yahoo Finance OHLCV chart endpoint.

    This is useful for quick agent-side market prices, but Yahoo Finance is
    unofficial and should not replace canonical BCB/CVM/B3/Tesouro sources.
    """
    return await chart.get_chart(symbol, range_, interval, include_pre_post)
