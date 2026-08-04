"""BCB PTAX and Focus source tests (no network; respx-mocked)."""

from __future__ import annotations

import re
from datetime import date

import httpx
import pytest
import respx

from findata.http_client import clear_cache
from findata.sources.bcb import focus, ptax


@pytest.fixture(autouse=True)
def _reset_http_cache() -> None:
    clear_cache()


_QUOTE = {
    "cotacaoCompra": 4.91,
    "cotacaoVenda": 4.92,
    "dataHoraCotacao": "2024-01-02 13:10:28.762",
}


def _mock_odata(endpoint: str, item: dict[str, object]) -> respx.Route:
    return respx.get(re.compile(rf"^{re.escape(endpoint)}(?:\?.*)?$")).mock(
        return_value=httpx.Response(200, json={"value": [item]})
    )


@respx.mock
async def test_get_ptax_usd_uses_fixed_date_and_parses_quote() -> None:
    route = _mock_odata(f"{ptax.BASE_URL}/CotacaoDolarDia(dataCotacao=@dataCotacao)", _QUOTE)

    quotes = await ptax.get_ptax_usd(date(2024, 1, 2))

    assert route.called
    assert route.calls.last.request.url.params["@dataCotacao"] == "'01-02-2024'"
    assert quotes[0].model_dump() == {
        "cotacao_compra": 4.91,
        "cotacao_venda": 4.92,
        "data_hora_cotacao": "2024-01-02 13:10:28.762",
    }


@respx.mock
async def test_get_ptax_usd_period_sends_both_dates() -> None:
    endpoint = (
        f"{ptax.BASE_URL}/CotacaoDolarPeriodo("
        "dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
    )
    route = _mock_odata(endpoint, _QUOTE)

    quotes = await ptax.get_ptax_usd_period(date(2024, 1, 2), date(2024, 1, 5))

    params = route.calls.last.request.url.params
    assert params["@dataInicial"] == "'01-02-2024'"
    assert params["@dataFinalCotacao"] == "'01-05-2024'"
    assert quotes[0].cotacao_venda == 4.92


@respx.mock
async def test_get_ptax_currency_normalizes_symbol() -> None:
    endpoint = f"{ptax.BASE_URL}/CotacaoMoedaDia(moeda=@moeda,dataCotacao=@dataCotacao)"
    route = _mock_odata(endpoint, _QUOTE)

    quotes = await ptax.get_ptax_currency("eur", date(2024, 1, 2))

    params = route.calls.last.request.url.params
    assert params["@moeda"] == "'EUR'"
    assert params["@dataCotacao"] == "'01-02-2024'"
    assert quotes[0].cotacao_compra == 4.91


@respx.mock
async def test_get_currencies_parses_olinda_fields() -> None:
    route = _mock_odata(
        f"{ptax.BASE_URL}/Moedas",
        {"simbolo": "EUR", "nomeFormatado": "Euro", "tipoMoeda": "B"},
    )

    currencies = await ptax.get_currencies()

    assert route.called
    assert currencies[0].model_dump() == {
        "simbolo": "EUR",
        "nome": "Euro",
        "tipo_moeda": "B",
    }


_EXPECTATION = {
    "Indicador": "IPCA",
    "Data": "2024-01-02",
    "DataReferencia": "2024",
    "Media": 3.91,
    "Mediana": 3.90,
    "DesvioPadrao": 0.42,
    "Minimo": 3.10,
    "Maximo": 4.80,
    "numeroRespondentes": 123,
    "baseCalculo": 0,
}


@pytest.mark.parametrize(
    ("fetch", "endpoint"),
    [
        (focus.get_focus_annual, "ExpectativasMercadoAnuais"),
        (focus.get_focus_monthly, "ExpectativaMercadoMensais"),
        (focus.get_focus_top5_annual, "ExpectativasMercadoTop5Anuais"),
    ],
)
@respx.mock
async def test_get_focus_expectations_parse_and_filter(fetch: object, endpoint: str) -> None:
    route = _mock_odata(f"{focus.BASE_URL}/{endpoint}", _EXPECTATION)

    rows = await fetch("ipca", top=5)  # type: ignore[operator]

    params = route.calls.last.request.url.params
    assert params["$top"] == "5"
    assert params["$orderby"] == "Data desc"
    assert params["$filter"] == "Indicador eq 'IPCA'"
    assert rows[0].model_dump() == {
        "indicador": "IPCA",
        "data": "2024-01-02",
        "data_referencia": "2024",
        "media": 3.91,
        "mediana": 3.90,
        "desvio_padrao": 0.42,
        "minimo": 3.10,
        "maximo": 4.80,
        "numero_respondentes": 123,
        "base_calculo": 0,
    }


@respx.mock
async def test_get_focus_selic_parses_meeting_expectation() -> None:
    route = _mock_odata(
        f"{focus.BASE_URL}/ExpectativasMercadoSelic",
        {
            "Indicador": "Selic",
            "Data": "2024-01-02",
            "Reuniao": "R1/2024",
            "Media": 11.75,
            "Mediana": 11.75,
            "Minimo": 11.50,
            "Maximo": 12.00,
        },
    )

    rows = await focus.get_focus_selic(top=5)

    params = route.calls.last.request.url.params
    assert params["$top"] == "5"
    assert params["$orderby"] == "Data desc"
    assert rows[0].model_dump() == {
        "indicador": "Selic",
        "data": "2024-01-02",
        "reuniao": "R1/2024",
        "media": 11.75,
        "mediana": 11.75,
        "minimo": 11.50,
        "maximo": 12.00,
    }
