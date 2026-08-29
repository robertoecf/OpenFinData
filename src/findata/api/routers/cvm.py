"""CVM API routes — companies, financial statements, funds."""

from __future__ import annotations

from datetime import date
from typing import TypeVar

from fastapi import APIRouter, Query

from findata.sources.cvm import (
    FundCadastro,
    companies,
    fca,
    fidc,
    fii,
    financials,
    fip,
    funds,
    get_fund_cadastro,
    holdings,
    ipe,
    lamina,
    profile,
)

router = APIRouter(prefix="/cvm", tags=["CVM"])

_CURRENT_YEAR = date.today().year

_T = TypeVar("_T")


def _page(items: list[_T], skip: int, limit: int) -> list[_T]:
    return items[skip : skip + limit]


# ── Companies ──────────────────────────────────────────────────────


@router.get("/companies")
async def list_companies(
    only_active: bool = Query(default=True),
    skip: int = Query(default=0, ge=0, description="Records to skip"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max records to return"),
) -> list[companies.Company]:
    """List all companies registered at CVM (paginated)."""
    return _page(await companies.get_companies(only_active), skip, limit)


@router.get("/companies/search")
async def search_companies(
    q: str = Query(..., min_length=2, description="Search query"),
    only_active: bool = Query(default=True),
) -> list[companies.Company]:
    """Search companies by name."""
    return await companies.search_company(q, only_active)


# ── Financial Statements ───────────────────────────────────────────


@router.get("/financials/dfp")
async def get_dfp(
    year: int = Query(..., ge=2010, le=_CURRENT_YEAR),
    statement: financials.StatementType = Query(default=financials.StatementType.DRE_CON),
    cnpj: str | None = Query(default=None, description="Filter by CNPJ (recommended)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[financials.FinancialEntry]:
    """Fetch annual financial statements (DFP) from CVM.

    Statement types: BPA_con, BPP_con, DRE_con, DFC_MI_con, DMPL_con, DVA_con
    (and _ind variants for individual/non-consolidated).

    **Tip**: Always pass `cnpj` to avoid downloading the entire dataset.
    """
    return _page(await financials.get_dfp(year, statement, cnpj), skip, limit)


@router.get("/financials/itr")
async def get_itr(
    year: int = Query(..., ge=2011, le=_CURRENT_YEAR),
    statement: financials.StatementType = Query(default=financials.StatementType.DRE_CON),
    cnpj: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[financials.FinancialEntry]:
    """Fetch quarterly financial statements (ITR) from CVM."""
    return _page(await financials.get_itr(year, statement, cnpj), skip, limit)


# ── IPE — Fatos relevantes / comunicados ──────────────────────────


@router.get("/companies/ipe")
async def list_ipe(
    year: int = Query(..., ge=2003, le=_CURRENT_YEAR + 1),
    cnpj: str | None = Query(default=None, description="Filter by issuer CNPJ"),
    categoria: str | None = Query(
        default=None,
        description='e.g. "Fato Relevante", "Comunicado ao Mercado", "Assembleia"',
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[ipe.IPEDocument]:
    """Stream of corporate filings (IPE — Informações Periódicas e Eventuais).

    Each row is one document: fato relevante, comunicado, ata, calendário,
    boletim de voto a distância, etc. Includes a direct download link to
    the original PDF on CVM's RAD system.
    """
    return _page(await ipe.get_ipe(year, cnpj=cnpj, categoria=categoria), skip, limit)


# ── FCA — Formulário Cadastral ────────────────────────────────────


@router.get("/companies/fca/geral")
async def fca_geral(
    year: int = Query(..., ge=2010, le=_CURRENT_YEAR + 1),
    cnpj: str | None = Query(default=None),
) -> list[fca.FCAGeneral]:
    """Top-level company facts: setor, situação registro, exercício social, website."""
    return await fca.get_fca_geral(year, cnpj)


@router.get("/companies/fca/securities")
async def fca_securities(
    year: int = Query(..., ge=2010, le=_CURRENT_YEAR + 1),
    cnpj: str | None = Query(default=None),
    ticker: str | None = Query(
        default=None,
        description="Optional B3 ticker filter (e.g. PETR4, VALE3)",
    ),
) -> list[fca.FCASecurity]:
    """Issued securities — useful as a B3-ticker → CNPJ resolver."""
    return await fca.get_fca_valores_mobiliarios(year, cnpj=cnpj, ticker=ticker)


@router.get("/companies/fca/dri")
async def fca_dri(
    year: int = Query(..., ge=2010, le=_CURRENT_YEAR + 1),
    cnpj: str | None = Query(default=None),
) -> list[fca.FCAInvestorRelations]:
    """Diretor de Relações com Investidores (DRI) — IR contact card."""
    return await fca.get_fca_dri(year, cnpj)


# ── Funds ──────────────────────────────────────────────────────────


@router.get("/funds")
async def list_funds(
    only_active: bool = Query(default=True),
    classe: str | None = Query(default=None, description="Filter by class"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[funds.Fund]:
    """List funds from the legacy cad_fi.csv (non-RCVM175-adapted only)."""
    return _page(await funds.get_fund_catalog(only_active, classe), skip, limit)


@router.get("/funds/cadastro")
async def fund_cadastro(
    cnpj: str | None = Query(default=None, description="Fund CNPJ (punctuated or digits)"),
    q: str | None = Query(default=None, min_length=2, description="Name fragment"),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[FundCadastro]:
    """RCVM 175 cadastral lookup (fundo + classe + subclasse). Requires cnpj or q."""
    return await get_fund_cadastro(cnpj=cnpj, q=q, limit=limit)


@router.get("/funds/daily")
async def fund_daily(
    year: int = Query(..., ge=2021, le=_CURRENT_YEAR + 1),
    month: int = Query(..., ge=1, le=12),
    cnpj: str | None = Query(default=None, description="Filter by fund CNPJ (recommended)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[funds.FundDaily]:
    """Fetch daily fund data (NAV, quota, flows) for a given month.

    **Tip**: Always pass `cnpj` to avoid loading the entire monthly file.
    """
    return _page(await funds.get_fund_daily(year, month, cnpj), skip, limit)


# ── CDA — Composição da Carteira ─────────────────────────────────


@router.get("/funds/holdings")
async def fund_holdings(
    cnpj: str = Query(..., description="Fund CNPJ (mandatory — file is huge)"),
    year: int = Query(..., ge=2018, le=_CURRENT_YEAR + 1),
    month: int = Query(..., ge=1, le=12),
    blocks: str | None = Query(
        default=None,
        description="Comma-separated block whitelist (BLC_1..BLC_8, CONFID, PL, FIE)",
    ),
) -> list[holdings.FundHolding]:
    """Fund portfolio (every position) for the given month.

    The CDA monthly file is ~150 MB unzipped, so a CNPJ filter is required.
    Use `blocks=BLC_1,BLC_4` to limit to specific asset classes.
    """
    block_list = [b.strip() for b in blocks.split(",")] if blocks else None
    return await holdings.get_fund_holdings(cnpj, year, month, block_list)


# ── LAMINA — Factsheet ───────────────────────────────────────────


@router.get("/funds/lamina")
async def fund_lamina(
    year: int = Query(..., ge=2018, le=_CURRENT_YEAR + 1),
    month: int = Query(..., ge=1, le=12),
    cnpj: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=5000),
) -> list[lamina.FundLamina]:
    """Fund regulatory factsheet — strategy, restrictions, alavancagem caps."""
    return _page(await lamina.get_fund_lamina(year, month, cnpj), skip, limit)


@router.get("/funds/lamina/returns/monthly")
async def fund_lamina_monthly(
    year: int = Query(..., ge=2018, le=_CURRENT_YEAR + 1),
    month: int = Query(..., ge=1, le=12),
    cnpj: str | None = Query(default=None),
) -> list[lamina.FundLaminaReturnMonth]:
    """Per-month returns published with the lâmina."""
    return await lamina.get_fund_monthly_returns(year, month, cnpj)


@router.get("/funds/lamina/returns/yearly")
async def fund_lamina_yearly(
    year: int = Query(..., ge=2018, le=_CURRENT_YEAR + 1),
    month: int = Query(..., ge=1, le=12),
    cnpj: str | None = Query(default=None),
) -> list[lamina.FundLaminaReturnYear]:
    """Per-year returns published with the lâmina."""
    return await lamina.get_fund_yearly_returns(year, month, cnpj)


# ── PERFIL_MENSAL — Investor breakdown ───────────────────────────


@router.get("/funds/profile")
async def fund_profile(
    year: int = Query(..., ge=2018, le=_CURRENT_YEAR + 1),
    month: int = Query(..., ge=1, le=12),
    cnpj: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[profile.FundProfile]:
    """Investor profile breakdown (cotistas por tipo) for the given month."""
    return _page(await profile.get_fund_profile(year, month, cnpj), skip, limit)


# ── FII — Fundos Imobiliários ────────────────────────────────────


@router.get("/funds/fii/geral")
async def fii_geral(
    year: int = Query(..., ge=2016, le=_CURRENT_YEAR + 1),
    cnpj: str | None = Query(default=None),
    month: int | None = Query(default=None, ge=1, le=12),
) -> list[fii.FIIGeneral]:
    """FII cadastral facet — segmento, mandato, gestão, administrador."""
    return await fii.get_fii_geral(year, cnpj=cnpj, month=month)


@router.get("/funds/fii/complemento")
async def fii_complemento(
    year: int = Query(..., ge=2016, le=_CURRENT_YEAR + 1),
    cnpj: str | None = Query(default=None),
    month: int | None = Query(default=None, ge=1, le=12),
) -> list[fii.FIIComplement]:
    """FII complement facet — cotistas breakdown + PL + taxa administração."""
    return await fii.get_fii_complemento(year, cnpj=cnpj, month=month)


# ── FIDC — Fundos de Direitos Creditórios ────────────────────────


@router.get("/funds/fidc/geral")
async def fidc_geral(
    year: int = Query(..., ge=2025, le=_CURRENT_YEAR + 1),
    month: int = Query(..., ge=1, le=12),
    cnpj: str | None = Query(default=None),
) -> list[fidc.FIDCGeneral]:
    """FIDC cadastral facet (TAB I) — admin, classe, condomínio."""
    return await fidc.get_fidc_geral(year, month, cnpj=cnpj)


@router.get("/funds/fidc/pl")
async def fidc_pl(
    year: int = Query(..., ge=2025, le=_CURRENT_YEAR + 1),
    month: int = Query(..., ge=1, le=12),
    cnpj: str | None = Query(default=None),
) -> list[fidc.FIDCPatrimonio]:
    """FIDC patrimônio líquido (TAB IV) — final + médio."""
    return await fidc.get_fidc_pl(year, month, cnpj=cnpj)


@router.get("/funds/fidc/direitos-creditorios")
async def fidc_direitos_creditorios(
    year: int = Query(..., ge=2025, le=_CURRENT_YEAR + 1),
    month: int = Query(..., ge=1, le=12),
    cnpj: str | None = Query(default=None),
) -> list[fidc.FIDCDireitosCreditorios]:
    """FIDC direitos creditórios (TAB VII) — com / sem risco + vencidos."""
    return await fidc.get_fidc_direitos_creditorios(year, month, cnpj=cnpj)


# ── FIP — Fundos de Investimento em Participações ────────────────


@router.get("/funds/fip")
async def fip_informe(
    year: int = Query(..., ge=2010, le=_CURRENT_YEAR + 1),
    cnpj: str | None = Query(default=None),
    quarter: int | None = Query(default=None, ge=1, le=4),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[fip.FIPInforme]:
    """FIP informe trimestral — capital, cotistas breakdown, classe."""
    return _page(await fip.get_fip(year, cnpj=cnpj, quarter=quarter), skip, limit)


# ── Period discovery ─────────────────────────────────────────────


@router.get("/funds/periods")
async def fund_periods(
    product: str = Query(
        default="INF_DIARIO",
        description="One of: INF_DIARIO, CDA, LAMINA, PERFIL_MENSAL, BALANCETE, EVENTUAL, EXTRATO",
    ),
) -> list[str]:
    """List the YYYYMM (or YYYY) stamps actually available upstream."""
    from findata.sources.cvm import _directory

    return await _directory.list_periods("FI", f"DOC/{product}")
