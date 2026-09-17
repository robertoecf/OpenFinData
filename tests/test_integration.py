"""Integration tests that hit live public APIs.

Skipped by default. Run with:   pytest -m integration
"""

from __future__ import annotations

from datetime import date

import pytest

from findata.sources.bcb import focus, ptax, sgs
from findata.sources.ibge import get_indicator, get_ipca_breakdown

pytestmark = pytest.mark.integration


class TestSGS:
    async def test_get_series_last_selic(self) -> None:
        data = await sgs.get_series_last(432, n=5)
        assert len(data) == 5
        assert all(d.valor > 0 for d in data)

    async def test_get_series_by_name(self) -> None:
        data = await sgs.get_series_by_name("ipca", n=3)
        assert len(data) == 3

    async def test_catalog_has_expected_keys(self) -> None:
        expected = {"selic", "ipca", "cdi", "dolar_ptax", "igpm"}
        assert expected.issubset(set(sgs.SERIES_CATALOG.keys()))


class TestPTAX:
    async def test_get_currencies(self) -> None:
        currencies = await ptax.get_currencies()
        assert len(currencies) > 0
        symbols = [c.simbolo for c in currencies]
        assert "USD" in symbols
        assert "EUR" in symbols

    async def test_get_ptax_usd_weekday(self) -> None:
        data = await ptax.get_ptax_usd(date(2026, 3, 27))  # Friday
        assert len(data) > 0
        assert data[0].cotacao_venda > 0

    async def test_get_ptax_usd_weekend_returns_empty(self) -> None:
        data = await ptax.get_ptax_usd(date(2026, 3, 28))  # Saturday
        assert len(data) == 0


class TestFocus:
    async def test_focus_annual_ipca(self) -> None:
        data = await focus.get_focus_annual("IPCA", top=5)
        assert len(data) == 5
        assert all(e.indicador == "IPCA" for e in data)

    async def test_focus_selic(self) -> None:
        data = await focus.get_focus_selic(top=5)
        assert len(data) == 5
        assert all(e.reuniao for e in data)


class TestIBGE:
    async def test_get_ipca_mensal(self) -> None:
        data = await get_indicator("ipca_mensal", periods=3)
        assert len(data) > 0
        assert any(d.valor is not None for d in data)

    async def test_get_ipca_breakdown(self) -> None:
        data = await get_ipca_breakdown(periods=2)
        groups = {d.classificacao for d in data if d.classificacao}
        assert len(groups) >= 5


class TestIPEA:
    async def test_get_series_values(self) -> None:
        from findata.sources.ipea import get_series_values

        data = await get_series_values("BM12_TJOVER12", top=3)
        assert len(data) == 3
        assert all(p.sercodigo == "BM12_TJOVER12" for p in data)

    async def test_get_metadata(self) -> None:
        from findata.sources.ipea import get_metadata

        meta = await get_metadata("BM12_TJOVER12")
        assert meta is not None
        assert meta.sercodigo == "BM12_TJOVER12"
        assert "Selic" in meta.sernome or "selic" in meta.sernome.lower()

    async def test_search_series(self) -> None:
        from findata.sources.ipea import search_series

        results = await search_series("IPCA", top=5)
        assert len(results) > 0


class TestB3:
    async def test_get_quote_petr4(self) -> None:
        pytest.importorskip("yfinance")
        from findata.sources.b3 import quotes

        q = await quotes.get_quote("PETR4")
        assert q.ticker == "PETR4"
        assert q.preco is not None
        assert q.preco > 0

    async def test_get_history(self) -> None:
        pytest.importorskip("yfinance")
        from findata.sources.b3 import quotes

        data = await quotes.get_history("VALE3", period="5d")
        assert len(data) > 0
        assert all(p.close > 0 for p in data)

    async def test_listed_funds_etf_includes_spxr(self) -> None:
        from findata.sources.b3.listed_funds import get_listed_funds, lookup_listed_fund

        funds = await get_listed_funds("ETF")
        tickers = {fund.ticker for fund in funds}
        assert "SPXR11" in tickers
        assert "SPBZ11" in tickers
        found = await lookup_listed_fund("SPXR11", "ETF")
        assert found is not None
        assert found.type_fund == "ETF"
