"""Tesouro Direto historical price and rate tests."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from findata.http_client import clear_cache
from findata.sources.tesouro.bonds import (
    TESOURO_CSV_URL,
    _bonds_cache,
    get_bond_history,
    get_treasury_bonds,
    search_bonds,
)


@pytest.fixture(autouse=True)
def _clean_caches() -> None:
    clear_cache()
    _bonds_cache.invalidate()


_TESOURO_CSV = (
    "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;"
    "PU Compra Manha;PU Venda Manha;PU Base Manha\n"
    "Tesouro Selic;01/03/2029;02/01/2024;0,15;0,16;14500,25;14490,10;14510,00\n"
    "Tesouro IPCA+;15/05/2035;02/01/2024;5,50;5,60;2500,00;2490,00;2510,00\n"
    "Tesouro IPCA+;15/05/2035;03/01/2024;5,45;5,55;2510,00;2500,00;2520,00\n"
)


def _mock_tesouro_csv() -> None:
    respx.get(TESOURO_CSV_URL).mock(
        return_value=httpx.Response(200, content=_TESOURO_CSV.encode("utf-8"))
    )


@respx.mock
async def test_get_treasury_bonds_parses_and_filters_rows() -> None:
    _mock_tesouro_csv()

    rows = await get_treasury_bonds(
        tipo="selic",
        start=date(2024, 1, 2),
        end=date(2024, 1, 2),
    )

    assert len(rows) == 1
    bond = rows[0]
    assert bond.titulo == "Tesouro Selic 2029"
    assert bond.dt_vencimento == "2029-03-01"
    assert bond.dt_base == "2024-01-02"
    assert bond.taxa_compra == 0.15
    assert bond.pu_base == 14510.0


@respx.mock
async def test_get_bond_history_returns_matching_date_range() -> None:
    _mock_tesouro_csv()

    rows = await get_bond_history(
        "ipca+ 2035",
        start=date(2024, 1, 3),
        end=date(2024, 1, 3),
    )

    assert len(rows) == 1
    assert rows[0].dt_base == "2024-01-03"
    assert rows[0].taxa_venda == 5.55
    assert rows[0].pu_compra == 2510.0


@respx.mock
async def test_search_bonds_returns_unique_sorted_titles() -> None:
    _mock_tesouro_csv()

    assert await search_bonds("tesouro") == [
        "Tesouro IPCA+ 2035",
        "Tesouro Selic 2029",
    ]
