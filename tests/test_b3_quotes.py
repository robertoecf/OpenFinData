"""B3 quote tests with yfinance replaced by deterministic fakes."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from findata.sources.b3 import quotes


@pytest.mark.asyncio
async def test_get_quote_uses_yfinance_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    requested_tickers: list[str] = []

    class FakeTicker:
        def __init__(self, ticker: str) -> None:
            requested_tickers.append(ticker)
            self.info = {
                "longName": "Petroleo Brasileiro S.A.",
                "currentPrice": 38.42,
                "regularMarketChangePercent": 1.25,
                "regularMarketOpen": 37.9,
                "regularMarketDayHigh": 38.7,
                "regularMarketDayLow": 37.8,
                "regularMarketVolume": 12_345_678,
                "marketCap": 501_000_000_000,
                "sector": "Energy",
                "currency": "BRL",
            }

    monkeypatch.setattr(
        quotes,
        "_import_yfinance",
        lambda: SimpleNamespace(Ticker=FakeTicker),
    )

    result = await quotes.get_quote("petr4")

    assert requested_tickers == ["PETR4.SA"]
    assert result == quotes.StockQuote(
        ticker="PETR4",
        nome="Petroleo Brasileiro S.A.",
        preco=38.42,
        variacao_dia=1.25,
        abertura=37.9,
        maxima=38.7,
        minima=37.8,
        volume=12_345_678,
        market_cap=501_000_000_000,
        setor="Energy",
        moeda="BRL",
    )


@pytest.mark.asyncio
async def test_get_history_maps_yfinance_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, str]] = []

    class FakeHistory:
        def iterrows(self) -> Any:
            yield (
                datetime(2026, 7, 30),
                {
                    "Open": 37.991,
                    "High": 38.876,
                    "Low": 37.554,
                    "Close": 38.432,
                    "Volume": 9_876_543.0,
                },
            )

    class FakeTicker:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def history(self, *, period: str, interval: str) -> FakeHistory:
            calls.append((self.ticker, period, interval))
            return FakeHistory()

    monkeypatch.setattr(
        quotes,
        "_import_yfinance",
        lambda: SimpleNamespace(Ticker=FakeTicker),
    )

    result = await quotes.get_history("vale3.sa", period="5d", interval="1h")

    assert calls == [("VALE3.SA", "5d", "1h")]
    assert result == [
        quotes.StockHistoryPoint(
            date="2026-07-30",
            open=37.99,
            high=38.88,
            low=37.55,
            close=38.43,
            volume=9_876_543,
        )
    ]
