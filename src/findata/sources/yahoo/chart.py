"""Yahoo Finance chart endpoint (experimental, unofficial).

This module calls Yahoo's public ``v8/finance/chart`` endpoint directly. It is
useful for quick market-price retrieval, but it is not an official data source
and may change or rate-limit without notice.
"""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel

from findata.http_client import get_json

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

VALID_RANGES = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
VALID_INTERVALS = {
    "1m",
    "2m",
    "5m",
    "15m",
    "30m",
    "60m",
    "90m",
    "1h",
    "1d",
    "5d",
    "1wk",
    "1mo",
    "3mo",
}


class YahooChartPoint(BaseModel):
    """One OHLCV point returned by Yahoo Finance."""

    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    adj_close: float | None = None
    volume: int | None = None


class YahooChart(BaseModel):
    """Normalized chart response from Yahoo Finance."""

    symbol: str
    currency: str | None = None
    exchange_name: str | None = None
    instrument_type: str | None = None
    timezone: str | None = None
    query_range: str | None = None
    interval: str
    source: str = "Yahoo Finance v8 chart (unofficial, best-effort)"
    points: list[YahooChartPoint]


def _as_float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _as_int(value: object) -> int | None:
    return int(value) if isinstance(value, int | float) else None


def _timezone(name: str | None) -> tzinfo:
    if not name:
        return UTC
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return UTC


def _timestamp_label(timestamp: int, timezone_name: str | None, interval: str) -> str:
    """Return a date for daily+ candles and local ISO datetime for intraday candles."""
    dt = datetime.fromtimestamp(timestamp, tz=_timezone(timezone_name))
    if interval in {"1d", "5d", "1wk", "1mo", "3mo"}:
        return dt.date().isoformat()
    return dt.replace(microsecond=0).isoformat()


def _validate_range_interval(range_: str, interval: str) -> None:
    if range_ not in VALID_RANGES:
        valid = sorted(VALID_RANGES)
        raise ValueError(f"Unsupported Yahoo range '{range_}'. Valid values: {valid}")
    if interval not in VALID_INTERVALS:
        raise ValueError(
            f"Unsupported Yahoo interval '{interval}'. Valid values: {sorted(VALID_INTERVALS)}"
        )


def _extract_result(payload: dict[str, Any], symbol: str) -> dict[str, Any]:
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise ValueError("Unexpected Yahoo response: missing chart object")

    error = chart.get("error")
    if error:
        description = error.get("description") if isinstance(error, dict) else str(error)
        raise ValueError(f"Yahoo Finance error for {symbol}: {description}")

    results = chart.get("result")
    if not isinstance(results, list) or not results:
        raise ValueError(f"Yahoo Finance returned no chart data for {symbol}")
    result = results[0]
    if not isinstance(result, dict):
        raise ValueError("Unexpected Yahoo response: chart result is not an object")
    return result


def _quote_values(result: dict[str, Any]) -> dict[str, list[Any]]:
    indicators = result.get("indicators")
    if not isinstance(indicators, dict):
        return {}
    quotes = indicators.get("quote")
    if not isinstance(quotes, list) or not quotes or not isinstance(quotes[0], dict):
        return {}
    return quotes[0]


def _adj_close_values(result: dict[str, Any]) -> list[Any]:
    indicators = result.get("indicators")
    if not isinstance(indicators, dict):
        return []
    adjclose = indicators.get("adjclose")
    if not isinstance(adjclose, list) or not adjclose or not isinstance(adjclose[0], dict):
        return []
    values = adjclose[0].get("adjclose")
    return values if isinstance(values, list) else []


def _value_at(values: dict[str, list[Any]], key: str, index: int) -> object:
    series = values.get(key, [])
    return series[index] if index < len(series) else None


async def get_chart(
    symbol: str,
    range_: str = "1mo",
    interval: str = "1d",
    include_pre_post: bool = False,
) -> YahooChart:
    """Fetch a normalized OHLCV chart from Yahoo Finance.

    Args:
        symbol: Yahoo symbol, e.g. ``PETR4.SA``, ``^BVSP``, ``BTC-USD``.
        range_: Yahoo range, e.g. ``1mo``, ``1y``, ``ytd``.
        interval: Yahoo interval, e.g. ``1d``, ``1wk``, ``1h``.
        include_pre_post: Whether to ask Yahoo for pre/post-market candles.
    """
    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise ValueError("Yahoo symbol is required")
    _validate_range_interval(range_, interval)

    payload = await get_json(
        CHART_URL.format(symbol=clean_symbol),
        params={
            "range": range_,
            "interval": interval,
            "events": "div,splits",
            "includePrePost": str(include_pre_post).lower(),
        },
    )
    if not isinstance(payload, dict):
        raise ValueError("Unexpected Yahoo response: JSON root is not an object")

    result = _extract_result(payload, clean_symbol)
    raw_meta = result.get("meta")
    meta = cast(dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else {}
    timezone_name = meta.get("exchangeTimezoneName")
    timestamps = result.get("timestamp")
    if not isinstance(timestamps, list):
        timestamps = []

    quote = _quote_values(result)
    adj_close = _adj_close_values(result)
    points: list[YahooChartPoint] = []
    for index, ts in enumerate(timestamps):
        if not isinstance(ts, int):
            continue
        points.append(
            YahooChartPoint(
                date=_timestamp_label(
                    ts, timezone_name if isinstance(timezone_name, str) else None, interval
                ),
                open=_as_float(_value_at(quote, "open", index)),
                high=_as_float(_value_at(quote, "high", index)),
                low=_as_float(_value_at(quote, "low", index)),
                close=_as_float(_value_at(quote, "close", index)),
                adj_close=_as_float(adj_close[index] if index < len(adj_close) else None),
                volume=_as_int(_value_at(quote, "volume", index)),
            )
        )

    return YahooChart(
        symbol=str(meta.get("symbol") or clean_symbol),
        currency=meta.get("currency") if isinstance(meta.get("currency"), str) else None,
        exchange_name=meta.get("fullExchangeName")
        if isinstance(meta.get("fullExchangeName"), str)
        else None,
        instrument_type=meta.get("instrumentType")
        if isinstance(meta.get("instrumentType"), str)
        else None,
        timezone=timezone_name if isinstance(timezone_name, str) else None,
        query_range=range_,
        interval=interval,
        points=points,
    )
