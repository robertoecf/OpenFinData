"""Thin API route smoke tests with all upstream traffic mocked."""

from __future__ import annotations

import re

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from findata.api.app import app
from findata.http_client import clear_cache
from findata.sources.cvm import companies
from findata.sources.tesouro import bonds


@pytest.fixture(autouse=True)
def _reset_module_caches() -> None:
    clear_cache()
    companies._companies_cache.invalidate()
    bonds._bonds_cache.invalidate()


def _client() -> TestClient:
    return TestClient(app)


@respx.mock
def test_ptax_usd_route() -> None:
    respx.get(re.compile(r"https://olinda\.bcb\.gov\.br/.*/CotacaoDolarDia.*")).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "cotacaoCompra": 4.91,
                        "cotacaoVenda": 4.92,
                        "dataHoraCotacao": "2024-01-02 13:10:00.000",
                    }
                ]
            },
        )
    )

    response = _client().get("/bcb/ptax/usd", params={"date": "2024-01-02"})

    assert response.status_code == 200
    assert response.json()[0]["cotacao_compra"] == 4.91


@respx.mock
def test_focus_annual_route() -> None:
    respx.get(re.compile(r"https://olinda\.bcb\.gov\.br/.*/ExpectativasMercadoAnuais.*")).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "Indicador": "IPCA",
                        "Data": "2024-01-02",
                        "DataReferencia": "2024",
                        "Media": 3.9,
                        "Mediana": 3.8,
                    }
                ]
            },
        )
    )

    response = _client().get("/bcb/focus/annual", params={"indicator": "IPCA"})

    assert response.status_code == 200
    assert response.json()[0]["indicador"] == "IPCA"


@respx.mock
def test_ibge_indicator_route() -> None:
    respx.get(re.compile(r"https://servicodados\.ibge\.gov\.br/api/v3/agregados/7060/.*")).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "variavel": "IPCA - Variação mensal",
                    "resultados": [
                        {
                            "classificacoes": [],
                            "series": [
                                {
                                    "localidade": {"nome": "Brasil"},
                                    "serie": {"202401": "0.42"},
                                }
                            ],
                        }
                    ],
                }
            ],
        )
    )

    response = _client().get("/ibge/indicators/ipca_mensal", params={"periods": 1})

    assert response.status_code == 200
    assert response.json()[0]["periodo"] == "202401"


@respx.mock
def test_tesouro_bonds_route() -> None:
    csv_data = (
        b"Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;"
        b"PU Compra Manha;PU Venda Manha;PU Base Manha\n"
        b"Tesouro Selic;01/03/2029;02/01/2024;0,10;0,11;100,00;99,00;99,50\n"
    )
    respx.get(bonds.TESOURO_CSV_URL).mock(return_value=httpx.Response(200, content=csv_data))

    response = _client().get("/tesouro/bonds", params={"tipo": "Selic"})

    assert response.status_code == 200
    assert response.json()[0]["tipo"] == "Tesouro Selic"


@respx.mock
def test_cvm_companies_route() -> None:
    csv_data = (
        "CNPJ_CIA;DENOM_SOCIAL;DENOM_COMERC;CD_CVM;SIT;SETOR_ATIV;CATEG_REG;CONTROLE_ACIONARIO\n"
        "00.000.000/0001-00;Companhia Teste SA;Teste;1234;ATIVO;Financeiro;A;PRIVADO\n"
    ).encode("iso-8859-1")
    respx.get(companies.COMPANIES_URL).mock(return_value=httpx.Response(200, content=csv_data))

    response = _client().get("/cvm/companies", params={"only_active": "true"})

    assert response.status_code == 200
    assert response.json()[0]["nome_social"] == "Companhia Teste SA"
