"""B3 listed-funds catalog (fundsListedProxy) — offline tests."""

from __future__ import annotations

import base64
import json
import re

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from findata.api.app import app
from findata.cli import app as cli_app
from findata.http_client import clear_cache
from findata.resolver import classify, resolve_asset
from findata.resolver.b3_catalog import classification_from_listed_fund
from findata.resolver.normalize import normalize
from findata.sources.b3.listed_funds import (
    FUND_TYPES,
    FUNDS_LISTED_PROXY,
    ListedFund,
    _encode_query,
    acronym_from_ticker,
    get_listed_funds,
    list_fund_types,
    listed_share_ticker,
    lookup_listed_fund,
)

_LIST_URL = re.compile(
    r"https://sistemaswebb3-listados\.b3\.com\.br/fundsListedProxy/Search/GetListFunds/.+"
)
runner = CliRunner()


@pytest.fixture(autouse=True)
def _clean_caches() -> None:
    clear_cache()


def _decode_request(request: httpx.Request) -> dict[str, object]:
    encoded = request.url.path.rsplit("/", 1)[-1]
    return json.loads(base64.b64decode(encoded).decode("utf-8"))


def _page(
    *rows: dict[str, object], page_number: int = 1, total_pages: int = 1
) -> dict[str, object]:
    return {
        "page": {
            "pageNumber": page_number,
            "pageSize": 100,
            "totalRecords": len(rows) if total_pages == 1 else 3,
            "totalPages": total_pages,
        },
        "results": list(rows),
    }


def test_encode_query_is_round_trippable_base64_json() -> None:
    encoded = _encode_query("etf-rf", page_number=2, keyword="LFTS")
    decoded = json.loads(base64.b64decode(encoded).decode("utf-8"))
    assert decoded["typeFund"] == "etf-rf"
    assert decoded["pageNumber"] == 2
    assert decoded["pageSize"] == 100
    assert decoded["language"] == "pt-br"
    assert decoded["keyword"] == "LFTS"
    assert encoded in f"{FUNDS_LISTED_PROXY}/{encoded}"


def test_acronym_and_listed_ticker_round_trip() -> None:
    assert acronym_from_ticker("spxr11") == "SPXR"
    assert acronym_from_ticker("SPBZ") == "SPBZ"
    assert listed_share_ticker("SPXR") == "SPXR11"
    assert listed_share_ticker("ABCDE") == "ABCDE"


async def test_list_fund_types_is_a_copy() -> None:
    types = await list_fund_types()
    assert types["ETF"] == "ETFs de Renda Variável"
    assert types["ETF-RF"] == "ETFs de Renda Fixa"
    assert types["FI-INFRA"] == FUND_TYPES["FI-INFRA"]
    assert types is not FUND_TYPES


@respx.mock
async def test_get_listed_funds_maps_rows_and_paginates() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        query = _decode_request(request)
        assert query["typeFund"] == "ETF"
        if query["pageNumber"] == 1:
            return httpx.Response(
                200,
                json=_page(
                    {
                        "id": 23167,
                        "typeName": None,
                        "acronym": "SPBZ",
                        "fundName": "BTG PACTUAL S&P 500 FUTURES QUANTO BRL FUNDO DE ÍNDICE",
                        "tradingName": "BTG SPHEDGE",
                    },
                    {
                        "id": 990,
                        "acronym": "BOVA",
                        "fundName": "ISHARES IBOVESPA",
                        "tradingName": "ISHARES BOVA",
                    },
                    total_pages=2,
                    page_number=1,
                ),
            )
        return httpx.Response(
            200,
            json=_page(
                {
                    "id": 16037,
                    "acronym": "SPXR",
                    "fundName": "IT NOW S&P 500 FUTURES QUANTO BRL FUNDO DE ÍNDICE",
                    "tradingName": "IT NOW SP BR",
                },
                page_number=2,
                total_pages=2,
            ),
        )

    respx.get(_LIST_URL).mock(side_effect=_handler)
    funds = await get_listed_funds("etf")
    tickers = [fund.ticker for fund in funds]
    assert tickers == ["SPBZ11", "BOVA11", "SPXR11"]
    spbz = funds[0]
    assert spbz.type_fund == "ETF"
    assert spbz.b3_id == 23167
    assert spbz.description == "ETFs de Renda Variável"


@respx.mock
async def test_lookup_prefers_etf_over_later_types() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        query = _decode_request(request)
        if query["typeFund"] == "ETF" and query["keyword"] == "SPXR":
            return httpx.Response(
                200,
                json=_page(
                    {
                        "id": 16037,
                        "acronym": "SPXR",
                        "fundName": "IT NOW S&P 500 FUTURES QUANTO BRL FUNDO DE ÍNDICE",
                        "tradingName": "IT NOW SP BR",
                    }
                ),
            )
        return httpx.Response(200, json=_page())

    respx.get(_LIST_URL).mock(side_effect=_handler)
    fund = await lookup_listed_fund("SPXR11")
    assert fund is not None
    assert fund.type_fund == "ETF"
    assert fund.ticker == "SPXR11"


@respx.mock
async def test_lookup_miss_returns_none() -> None:
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=_page()))
    assert await lookup_listed_fund("ZZZZ11") is None


@respx.mock
async def test_catalog_miss_does_not_keep_suffix_11_fii() -> None:
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=_page()))
    from findata.resolver import b3_listed_provider

    offline = classify(normalize(ticker="ZZZZ11"))
    assert offline.kind == "fii"
    result = await resolve_asset(ticker="ZZZZ11", providers=[b3_listed_provider])
    assert result.kind == "outro"
    assert result.macro_class == "Indefinido"
    assert result.source == "b3"
    assert result.signals[-1].detail == "not_listed"
    still_offline = await resolve_asset(ticker="ZZZZ11")
    assert still_offline.kind == "fii"
    assert still_offline.source == "openfindata"


async def test_unknown_type_is_value_error() -> None:
    with pytest.raises(ValueError, match="unknown B3 listed-fund type"):
        await get_listed_funds("NOT-A-TYPE")


def test_spbz11_offline_core_is_still_the_fii_heuristic() -> None:
    result = classify(normalize(ticker="SPBZ11"))
    assert result.kind == "fii"
    assert result.source == "openfindata"


@respx.mock
async def test_spbz11_with_b3_provider_is_etf_rv_internacional() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        query = _decode_request(request)
        if query["typeFund"] == "ETF" and query["keyword"] == "SPBZ":
            return httpx.Response(
                200,
                json=_page(
                    {
                        "id": 23167,
                        "acronym": "SPBZ",
                        "fundName": "BTG PACTUAL S&P 500 FUTURES QUANTO BRL FUNDO DE ÍNDICE",
                        "tradingName": "BTG SPHEDGE",
                    }
                ),
            )
        return httpx.Response(200, json=_page())

    respx.get(_LIST_URL).mock(side_effect=_handler)
    from findata.resolver import b3_listed_provider

    result = await resolve_asset(ticker="SPBZ11", providers=[b3_listed_provider])
    assert result.kind == "etf"
    assert result.macro_class == "Renda Variável"
    assert result.exposure == "Internacional"
    assert result.source == "b3"
    assert result.cascade[0] == "openfindata:rules"
    assert "b3:listed-funds" in result.cascade
    assert result.signals[-1].detail == "type=ETF"


def test_classification_maps_official_types() -> None:
    norm = normalize(ticker="IFRA11")
    fund = ListedFund(
        ticker="IFRA11",
        acronym="IFRA",
        fund_name="ITAÚ FIF INCEN EM INFRA",
        trading_name="FI ITAUINFRA",
        type_fund="FI-INFRA",
        description="FI-Infra",
    )
    result = classification_from_listed_fund(norm, fund)
    assert result.kind == "fundo"
    assert result.macro_class == "Renda Fixa"
    assert result.cvm.estrutura == "FI-INFRA"
    assert result.debenture is not None
    assert result.debenture.incentivada_1243 is True
    assert result.tax.isento is True


@respx.mock
def test_listed_funds_route_list_and_lookup() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        query = _decode_request(request)
        if query.get("keyword") == "LFTS":
            return httpx.Response(
                200,
                json=_page(
                    {
                        "id": 8806,
                        "acronym": "LFTS",
                        "fundName": "INVESTO TEVA TESOURO SELIC ETF",
                        "tradingName": "INVESTO LFTS",
                    }
                ),
            )
        if query["typeFund"] == "ETF-RF" and query["keyword"] == "":
            return httpx.Response(
                200,
                json=_page(
                    {
                        "id": 8806,
                        "acronym": "LFTS",
                        "fundName": "INVESTO TEVA TESOURO SELIC ETF",
                        "tradingName": "INVESTO LFTS",
                    }
                ),
            )
        return httpx.Response(200, json=_page())

    respx.get(_LIST_URL).mock(side_effect=_handler)
    client = TestClient(app)
    types = client.get("/b3/listed-funds")
    assert types.status_code == 200
    assert types.json()["ETF"] == "ETFs de Renda Variável"

    listed = client.get("/b3/listed-funds", params={"type": "ETF-RF"})
    assert listed.status_code == 200
    assert listed.json()[0]["ticker"] == "LFTS11"

    found = client.get("/b3/listed-funds", params={"ticker": "LFTS11", "type": "ETF-RF"})
    assert found.status_code == 200
    assert found.json()["type_fund"] == "ETF-RF"

    missing = client.get("/b3/listed-funds", params={"ticker": "ZZZZ11", "type": "ETF-RF"})
    assert missing.status_code == 404

    bad = client.get("/b3/listed-funds", params={"type": "NOPE"})
    assert bad.status_code == 400


@respx.mock
def test_resolver_route_uses_b3_catalog_for_unknown_11() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        query = _decode_request(request)
        if query["typeFund"] == "ETF" and query["keyword"] == "SPXR":
            return httpx.Response(
                200,
                json=_page(
                    {
                        "id": 16037,
                        "acronym": "SPXR",
                        "fundName": "IT NOW S&P 500 FUTURES QUANTO BRL FUNDO DE ÍNDICE",
                        "tradingName": "IT NOW SP BR",
                    }
                ),
            )
        return httpx.Response(200, json=_page())

    respx.get(_LIST_URL).mock(side_effect=_handler)
    client = TestClient(app)
    response = client.get("/resolver/resolve", params={"ticker": "SPXR11"})
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "etf"
    assert body["macro_class"] == "Renda Variável"
    assert body["source"] == "b3"


@respx.mock
def test_cli_listed_and_resolve() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        query = _decode_request(request)
        if query["typeFund"] == "ETF" and query["keyword"] == "SPBZ":
            return httpx.Response(
                200,
                json=_page(
                    {
                        "id": 23167,
                        "acronym": "SPBZ",
                        "fundName": "BTG PACTUAL S&P 500 FUTURES QUANTO BRL FUNDO DE ÍNDICE",
                        "tradingName": "BTG SPHEDGE",
                    }
                ),
            )
        return httpx.Response(200, json=_page())

    respx.get(_LIST_URL).mock(side_effect=_handler)
    listed = runner.invoke(cli_app, ["b3", "listed", "SPBZ11"])
    assert listed.exit_code == 0
    assert "SPBZ11" in listed.stdout
    assert "ETF" in listed.stdout

    types = runner.invoke(cli_app, ["b3", "listed"])
    assert types.exit_code == 0
    assert "ETF-RF" in types.stdout

    resolved = runner.invoke(cli_app, ["resolve", "SPBZ11"])
    assert resolved.exit_code == 0
    assert "Renda Variável" in resolved.stdout
    assert "etf" in resolved.stdout
