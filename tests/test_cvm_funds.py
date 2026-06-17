"""CVM fund-extras tests — directory listing, holdings, lamina, profile.

Network calls mocked with respx so tests stay deterministic and fast.
"""

from __future__ import annotations

import io
import re
import zipfile

import httpx
import pytest
import respx

from findata.http_client import clear_cache
from findata.sources.cvm._directory import _listing_cache
from findata.sources.cvm.holdings import _block_label, get_fund_holdings
from findata.sources.cvm.lamina import (
    get_fund_lamina,
    get_fund_monthly_returns,
    get_fund_yearly_returns,
)
from findata.sources.cvm.profile import get_fund_profile


@pytest.fixture(autouse=True)
def _clean_caches() -> None:
    clear_cache()
    _listing_cache.invalidate()


# ── Directory listing ────────────────────────────────────────────


_LISTING_HTML = """<html><body>
<a href="../">../</a>
<a href="cda_fi_202601.zip">cda_fi_202601.zip</a>     5.4M
<a href="cda_fi_202602.zip">cda_fi_202602.zip</a>     6.1M
<a href="cda_fi_202603.zip">cda_fi_202603.zip</a>     14M
</body></html>"""


@respx.mock
async def test_directory_list_files() -> None:
    respx.get("https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/").mock(
        return_value=httpx.Response(200, text=_LISTING_HTML)
    )
    from findata.sources.cvm._directory import list_files

    files = await list_files("FI", "DOC/CDA")
    assert files == ["cda_fi_202601.zip", "cda_fi_202602.zip", "cda_fi_202603.zip"]


@respx.mock
async def test_directory_list_periods() -> None:
    respx.get("https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/").mock(
        return_value=httpx.Response(200, text=_LISTING_HTML)
    )
    from findata.sources.cvm._directory import latest_period, list_periods

    periods = await list_periods("FI", "DOC/CDA")
    assert periods == ["202601", "202602", "202603"]
    latest = await latest_period("FI", "DOC/CDA")
    assert latest == "202603"


# ── CDA holdings ─────────────────────────────────────────────────


def test_block_label_decodes_filenames() -> None:
    assert _block_label("cda_fi_BLC_4_202603.csv") == "BLC_4"
    assert _block_label("cda_fi_BLC_8_202603.csv") == "BLC_8"
    assert _block_label("cda_fi_CONFID_202603.csv") == "CONFID"
    assert _block_label("cda_fi_PL_202603.csv") == "PL"
    assert _block_label("cda_fie_202603.csv") == "FIE"
    assert _block_label("cda_fie_CONFID_202603.csv") == "FIE_CONFID"


def _make_cda_zip() -> bytes:
    """Build a tiny valid CDA-shaped zip with two block CSVs."""
    blc4_header = (
        "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;TP_APLIC;"
        "TP_ATIVO;EMISSOR_LIGADO;TP_NEGOC;QT_POS_FINAL;VL_MERC_POS_FINAL;DS_ATIVO\n"
    )
    blc4_rows = (
        "FIF;12.345.678/0001-99;FUNDO TESTE;2026-03-31;Ações;Ação ordinária;"
        "N;Para negociação;1000;5000.50;PETR4\n"
        "FIF;12.345.678/0001-99;FUNDO TESTE;2026-03-31;Debêntures;Debênture simples;"
        "N;Para negociação;100;113146.46;CSAN33\n"
        "FIF;99.999.999/0001-00;OUTRO FUNDO;2026-03-31;Ações;Ação ordinária;"
        "N;Para negociação;500;2500;VALE3\n"
    )
    blc8_header = (
        "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;TP_APLIC;"
        "TP_ATIVO;TP_NEGOC;VL_MERC_POS_FINAL\n"
    )
    blc8_rows = (
        "FIF;12.345.678/0001-99;FUNDO TESTE;2026-03-31;Disponibilidades;"
        "Outros;Para negociação;9028.50\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("cda_fi_BLC_4_202603.csv", (blc4_header + blc4_rows).encode("iso-8859-1"))
        zf.writestr("cda_fi_BLC_8_202603.csv", (blc8_header + blc8_rows).encode("iso-8859-1"))
    return buf.getvalue()


@respx.mock
async def test_holdings_filter_by_cnpj() -> None:
    respx.get(re.compile(r"https://.*cda_fi_202603\.zip")).mock(
        return_value=httpx.Response(200, content=_make_cda_zip())
    )
    rows = await get_fund_holdings("12.345.678/0001-99", year=2026, month=3)
    assert len(rows) == 3  # 2 from BLC_4 + 1 from BLC_8 — other fund excluded
    assert {r.bloco for r in rows} == {"BLC_4", "BLC_8"}
    assert all(r.cnpj == "12.345.678/0001-99" for r in rows)
    assert rows[0].descricao == "PETR4"
    assert rows[0].valor_mercado == 5000.50


@respx.mock
async def test_holdings_block_whitelist() -> None:
    respx.get(re.compile(r"https://.*cda_fi_202603\.zip")).mock(
        return_value=httpx.Response(200, content=_make_cda_zip())
    )
    rows = await get_fund_holdings("12.345.678/0001-99", year=2026, month=3, blocks=["BLC_4"])
    assert len(rows) == 2
    assert all(r.bloco == "BLC_4" for r in rows)


@respx.mock
async def test_holdings_bare_digit_cnpj_matches_punctuated() -> None:
    """CVM stores CNPJs punctuated; a bare-digit query must still match.

    Regression: the reader used to compare raw strings, so ``12345678000199``
    never matched the stored ``12.345.678/0001-99`` and returned no holdings.
    """
    respx.get(re.compile(r"https://.*cda_fi_202603\.zip")).mock(
        return_value=httpx.Response(200, content=_make_cda_zip())
    )
    rows = await get_fund_holdings("12345678000199", year=2026, month=3)
    assert len(rows) == 3  # identical to the punctuated query
    assert {r.bloco for r in rows} == {"BLC_4", "BLC_8"}
    assert all(r.cnpj == "12.345.678/0001-99" for r in rows)  # output keeps CVM format


def _make_cda_blc2_zip() -> bytes:
    """BLC_2 (cotas de fundos) zip whose free-text name has a stray quote.

    The first invested-fund name opens a double-quote that is only closed on
    the next row. The default csv dialect treats ``"`` as a quote char, so it
    swallows the delimiter/newline and merges both rows into one — silently
    dropping the second fund-of-funds position. Real CDA files carry exactly
    this pattern, which made an entire FIC portfolio vanish.
    """
    header = (
        "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;TP_APLIC;"
        "TP_ATIVO;EMISSOR_LIGADO;QT_POS_FINAL;VL_MERC_POS_FINAL;DS_ATIVO\n"
    )
    rows = (
        "FIC;22.187.946/0001-41;VERDE FIC;2025-12-31;Cotas de Fundos;Cota de FI;"
        'N;850657.05;850657058.68;"VERDE MASTER FIC\n'
        "FIC;22.187.946/0001-41;VERDE FIC;2025-12-31;Cotas de Fundos;Cota de FI;"
        'N;100;500000.00;OUTRO" FUNDO INVESTIDO\n'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("cda_fi_BLC_2_202512.csv", (header + rows).encode("iso-8859-1"))
    return buf.getvalue()


@respx.mock
async def test_holdings_blc2_stray_quote_not_dropped() -> None:
    """A BLC_2 row with a stray quote in the fund name must not be dropped."""
    respx.get(re.compile(r"https://.*cda_fi_202512\.zip")).mock(
        return_value=httpx.Response(200, content=_make_cda_blc2_zip())
    )
    rows = await get_fund_holdings("22.187.946/0001-41", year=2025, month=12)
    assert len(rows) == 2  # both fund-of-funds positions survive parsing
    assert all(r.bloco == "BLC_2" for r in rows)
    assert rows[0].valor_mercado == 850657058.68  # ~99.8% of PL — the big one
    assert rows[1].valor_mercado == 500000.00
    # stray quote is kept literally, not treated as a CSV quote char
    assert rows[0].descricao == '"VERDE MASTER FIC'


# ── LAMINA ───────────────────────────────────────────────────────


def _make_lamina_zip() -> bytes:
    main_header = (
        "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;NM_FANTASIA;"
        "PUBLICO_ALVO;OBJETIVO;PR_PL_ATIVO_EXTERIOR;PR_PL_ATIVO_CRED_PRIV;"
        "PR_PL_ALAVANCAGEM\n"
    )
    main_row = (
        "FIF;12.345.678/0001-99;FUNDO TESTE;2026-03-31;TESTE FUND;"
        "Investidor qualificado;Render acima do CDI;5,5;12,3;0\n"
    )
    year_header = "CNPJ_FUNDO_CLASSE;DT_COMPTC;ANO_RENTAB;PR_RENTAB_ANO;PR_RENTAB_INDX;DS_INDX\n"
    year_row = "12.345.678/0001-99;2026-03-31;2025;13,45;13,12;CDI\n"
    month_header = "CNPJ_FUNDO_CLASSE;DT_COMPTC;MES;PR_RENTAB_MES;PR_RENTAB_INDX\n"
    month_row = "12.345.678/0001-99;2026-03-31;2026-03;1,1;0,98\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("lamina_fi_202603.csv", (main_header + main_row).encode("iso-8859-1"))
        zf.writestr(
            "lamina_fi_rentab_ano_202603.csv",
            (year_header + year_row).encode("iso-8859-1"),
        )
        zf.writestr(
            "lamina_fi_rentab_mes_202603.csv",
            (month_header + month_row).encode("iso-8859-1"),
        )
    return buf.getvalue()


@respx.mock
async def test_lamina_main() -> None:
    respx.get(re.compile(r"https://.*lamina_fi_202603\.zip")).mock(
        return_value=httpx.Response(200, content=_make_lamina_zip())
    )
    rows = await get_fund_lamina(2026, 3, cnpj="12.345.678/0001-99")
    assert len(rows) == 1
    f = rows[0]
    assert f.denom_social == "FUNDO TESTE"
    assert f.pct_pl_ativo_exterior == 5.5
    assert f.pct_pl_ativo_credito_privado == 12.3
    assert f.objetivo == "Render acima do CDI"


@respx.mock
async def test_lamina_returns() -> None:
    respx.get(re.compile(r"https://.*lamina_fi_202603\.zip")).mock(
        return_value=httpx.Response(200, content=_make_lamina_zip())
    )
    yearly = await get_fund_yearly_returns(2026, 3, cnpj="12.345.678/0001-99")
    assert yearly[0].ano == 2025
    assert yearly[0].rentabilidade_pct == 13.45
    assert yearly[0].bench_nome == "CDI"

    monthly = await get_fund_monthly_returns(2026, 3, cnpj="12.345.678/0001-99")
    assert monthly[0].mes_competencia == "2026-03"
    assert monthly[0].rentabilidade_pct == 1.1


# ── PERFIL_MENSAL ────────────────────────────────────────────────


_PERFIL_CSV = (
    "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;VERSAO;"
    "NR_COTST_PF_PB;NR_COTST_PF_VAREJO;NR_COTST_PJ_NAO_FINANC_PB;"
    "NR_COTST_PJ_NAO_FINANC_VAREJO;NR_COTST_BANCO;NR_COTST_CORRETORA_DISTRIB;"
    "NR_COTST_PJ_FINANC\n"
    "FIF;12.345.678/0001-99;FUNDO TESTE;2026-03-31;1;24;1491;4;50;0;0;0\n"
    "FIF;99.999.999/0001-00;OUTRO FUNDO;2026-03-31;1;100;200;5;10;0;0;1\n"
)


@respx.mock
async def test_profile_filter() -> None:
    respx.get(
        "https://dados.cvm.gov.br/dados/FI/DOC/PERFIL_MENSAL/DADOS/perfil_mensal_fi_202603.csv"
    ).mock(return_value=httpx.Response(200, text=_PERFIL_CSV))
    rows = await get_fund_profile(2026, 3, cnpj="12.345.678/0001-99")
    assert len(rows) == 1
    assert rows[0].cotistas_pf_varejo == 1491
    assert rows[0].cotistas_pj_nao_financ_varejo == 50


@respx.mock
async def test_profile_no_filter_returns_all() -> None:
    respx.get(
        "https://dados.cvm.gov.br/dados/FI/DOC/PERFIL_MENSAL/DADOS/perfil_mensal_fi_202603.csv"
    ).mock(return_value=httpx.Response(200, text=_PERFIL_CSV))
    rows = await get_fund_profile(2026, 3)
    assert len(rows) == 2
