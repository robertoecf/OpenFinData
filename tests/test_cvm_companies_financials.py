"""CVM company registration and annual financial statement tests."""

from __future__ import annotations

import io
import re
import zipfile

import httpx
import pytest
import respx

from findata.http_client import clear_cache
from findata.sources.cvm.companies import (
    COMPANIES_URL,
    _companies_cache,
    get_companies,
    search_company,
)
from findata.sources.cvm.financials import StatementType, get_dfp


@pytest.fixture(autouse=True)
def _clean_caches() -> None:
    clear_cache()
    _companies_cache.invalidate()


_COMPANIES_CSV = (
    "CNPJ_CIA;DENOM_SOCIAL;DENOM_COMERC;CD_CVM;SIT;SETOR_ATIV;CATEG_REG;"
    "CONTROLE_ACIONARIO\n"
    "33.592.510/0001-54;PETROLEO BRASILEIRO S.A. - PETROBRAS;PETROBRAS;9512;"
    "ATIVO;Petróleo e Gás;Categoria A;Estatal\n"
    "00.000.000/0001-91;BANCO ANTIGO S.A.;BANCO ANTIGO;1023;CANCELADA;Bancos;"
    "Categoria A;Privado\n"
)


@respx.mock
async def test_get_companies_active_and_inactive() -> None:
    respx.get(COMPANIES_URL).mock(
        return_value=httpx.Response(200, content=_COMPANIES_CSV.encode("iso-8859-1"))
    )

    active = await get_companies(only_active=True)
    all_companies = await get_companies(only_active=False)

    assert len(active) == 1
    assert active[0].nome_comercial == "PETROBRAS"
    assert {company.situacao for company in all_companies} == {"ATIVO", "CANCELADA"}


@respx.mock
async def test_search_company_by_social_or_commercial_name() -> None:
    respx.get(COMPANIES_URL).mock(
        return_value=httpx.Response(200, content=_COMPANIES_CSV.encode("iso-8859-1"))
    )

    by_social_name = await search_company("petroleo")
    by_commercial_name = await search_company("banco antigo", only_active=False)

    assert [company.cnpj for company in by_social_name] == ["33.592.510/0001-54"]
    assert [company.cnpj for company in by_commercial_name] == ["00.000.000/0001-91"]


_DFP_CSV = (
    "CNPJ_CIA;DENOM_CIA;CD_CVM;DT_REFER;VERSAO;CD_CONTA;DS_CONTA;VL_CONTA;"
    "MOEDA;ESCALA_MOEDA\n"
    "33.592.510/0001-54;PETROBRAS;9512;2024-12-31;1;3.01;Receita de Venda;"
    "not-a-number;REAL;MIL\n"
    "33.592.510/0001-54;PETROBRAS;9512;2024-12-31;1;3.02;Custo dos Produtos;"
    "-250.5;REAL;MIL\n"
    "00.000.000/0001-91;BANCO DO BRASIL;1023;2024-12-31;1;3.01;Receita;"
    "900;REAL;MIL\n"
)


def _make_dfp_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "dfp_cia_aberta_DRE_con_2024.csv",
            _DFP_CSV.encode("iso-8859-1"),
        )
    return buffer.getvalue()


@respx.mock
async def test_get_dfp_filters_cnpj_and_defaults_invalid_value_to_zero() -> None:
    respx.get(re.compile(r"https://.*dfp_cia_aberta_2024\.zip")).mock(
        return_value=httpx.Response(200, content=_make_dfp_zip())
    )

    rows = await get_dfp(
        2024,
        statement=StatementType.DRE_CON,
        cnpj="33.592.510/0001-54",
    )

    assert len(rows) == 2
    assert all(row.cnpj == "33.592.510/0001-54" for row in rows)
    assert rows[0].valor == 0.0
    assert rows[1].valor == -250.5
