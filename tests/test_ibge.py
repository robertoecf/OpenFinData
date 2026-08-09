"""IBGE Agregados source tests (no network; respx-mocked)."""

from __future__ import annotations

import re

import httpx
import pytest
import respx

from findata.http_client import clear_cache
from findata.sources.ibge import indicators


@pytest.fixture(autouse=True)
def _reset_http_cache() -> None:
    clear_cache()


def _ibge_payload(*, category: dict[str, str] | None = None) -> list[dict[str, object]]:
    classifications = []
    if category is not None:
        classifications = [{"id": "315", "nome": "Geral, grupo", "categoria": category}]
    return [
        {
            "id": "63",
            "variavel": "IPCA - Variação mensal",
            "resultados": [
                {
                    "classificacoes": classifications,
                    "series": [
                        {
                            "localidade": {"id": "1", "nome": "Brasil"},
                            "serie": {"202312": "0.56", "202401": "..."},
                        }
                    ],
                }
            ],
        }
    ]


@respx.mock
async def test_get_indicator_parses_series_and_missing_value() -> None:
    endpoint = f"{indicators.BASE_URL}/7060/periodos/-2/variaveis/63"
    route = respx.get(re.compile(rf"^{re.escape(endpoint)}(?:\?.*)?$")).mock(
        return_value=httpx.Response(200, json=_ibge_payload())
    )

    rows = await indicators.get_indicator("ipca_mensal", periods=2)

    assert route.calls.last.request.url.params["localidades"] == "N1[all]"
    assert len(rows) == 2
    assert set(rows[0].model_dump()) == {
        "periodo",
        "valor",
        "localidade",
        "variavel",
        "classificacao",
    }
    assert rows[0].model_dump() == {
        "periodo": "202312",
        "valor": 0.56,
        "localidade": "Brasil",
        "variavel": "IPCA - Variação mensal",
        "classificacao": None,
    }
    assert rows[1].valor is None


@respx.mock
async def test_get_ipca_breakdown_sends_groups_and_parses_classification() -> None:
    endpoint = f"{indicators.BASE_URL}/7060/periodos/-2/variaveis/63"
    route = respx.get(re.compile(rf"^{re.escape(endpoint)}(?:\?.*)?$")).mock(
        return_value=httpx.Response(
            200,
            json=_ibge_payload(category={"7170": "1.Alimentação e bebidas"}),
        )
    )

    rows = await indicators.get_ipca_breakdown(periods=2, groups=["7170", "7445"])

    params = route.calls.last.request.url.params
    assert params["localidades"] == "N1[all]"
    assert params["classificacao"] == "315[7170,7445]"
    assert set(rows[0].model_dump()) == {
        "periodo",
        "valor",
        "localidade",
        "variavel",
        "classificacao",
    }
    assert rows[0].classificacao == "1.Alimentação e bebidas"
