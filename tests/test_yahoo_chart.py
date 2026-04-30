"""Yahoo Finance chart adapter tests (no network; respx-mocked)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from findata.sources.yahoo import chart


def _sample_payload() -> dict[str, object]:
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": "BRL",
                        "symbol": "PETR4.SA",
                        "fullExchangeName": "São Paulo",
                        "instrumentType": "EQUITY",
                        "exchangeTimezoneName": "America/Sao_Paulo",
                    },
                    "timestamp": [1711929600, 1712016000],
                    "indicators": {
                        "quote": [
                            {
                                "open": [37.1, 37.5],
                                "high": [38.0, 38.2],
                                "low": [36.9, 37.0],
                                "close": [37.7, 38.1],
                                "volume": [1000, 2000],
                            }
                        ],
                        "adjclose": [{"adjclose": [37.2, 37.6]}],
                    },
                }
            ],
            "error": None,
        }
    }


@respx.mock
def test_get_chart_normalizes_yahoo_payload() -> None:
    respx.get("https://query1.finance.yahoo.com/v8/finance/chart/PETR4.SA").mock(
        return_value=httpx.Response(200, json=_sample_payload())
    )

    data = asyncio.run(chart.get_chart("petr4.sa", range_="1mo", interval="1d"))

    assert data.symbol == "PETR4.SA"
    assert data.currency == "BRL"
    assert data.exchange_name == "São Paulo"
    assert data.instrument_type == "EQUITY"
    assert data.query_range == "1mo"
    assert data.interval == "1d"
    assert len(data.points) == 2
    assert data.points[0].date == "2024-03-31"
    assert data.points[0].close == pytest.approx(37.7)
    assert data.points[1].volume == 2000


def test_get_chart_rejects_unknown_range() -> None:
    with pytest.raises(ValueError, match="Unsupported Yahoo range"):
        asyncio.run(chart.get_chart("PETR4.SA", range_="bad", interval="1d"))


@respx.mock
def test_get_chart_surfaces_yahoo_error() -> None:
    respx.get("https://query1.finance.yahoo.com/v8/finance/chart/PETR4.SA").mock(
        return_value=httpx.Response(
            200,
            json={
                "chart": {
                    "result": None,
                    "error": {"code": "Unprocessable Entity", "description": "range too old"},
                }
            },
        )
    )

    with pytest.raises(ValueError, match="range too old"):
        asyncio.run(chart.get_chart("PETR4.SA", range_="1mo", interval="1h"))

@respx.mock
def test_yahoo_api_route() -> None:
    from fastapi.testclient import TestClient

    from findata.api.app import app

    respx.get("https://query1.finance.yahoo.com/v8/finance/chart/PETR4.SA").mock(
        return_value=httpx.Response(200, json=_sample_payload())
    )

    response = TestClient(app).get(
        "/yahoo/chart/PETR4.SA", params={"range": "1mo", "interval": "1d"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "PETR4.SA"
    assert body["query_range"] == "1mo"
    assert body["points"][0]["close"] == 37.7
