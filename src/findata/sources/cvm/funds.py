"""CVM investment funds data.

Fund catalog: https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv (~17MB)
Daily NAV/quota: https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{YYYYMM}.zip
"""

from __future__ import annotations

from pydantic import BaseModel

from findata._cache import TTLCache
from findata.sources.cvm.parser import cnpj_digits, fetch_csv, fetch_csv_from_zip

FUND_CATALOG_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv"
FUND_DAILY_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{ym}.zip"


class Fund(BaseModel):
    cnpj: str
    nome: str
    classe: str
    situacao: str
    tipo: str
    fundo_cotas: str  # S/N
    exclusivo: str  # S/N
    patrimonio_liquido: float | None = None
    taxa_admin: str
    gestor: str
    administrador: str
    classe_anbima: str


class FundDaily(BaseModel):
    cnpj: str
    dt_comptc: str  # YYYY-MM-DD
    vl_total: float
    vl_quota: float
    vl_patrimonio_liq: float
    captacao_dia: float
    resgate_dia: float
    nr_cotistas: int
    tp_fundo_classe: str = ""
    id_subclasse: str = ""


# Parsed-data cache (avoids re-parsing the 17MB CSV on every call)
_catalog_cache: TTLCache[list[Fund]] = TTLCache(ttl=3600)


def _parse_fund_row(row: dict[str, str]) -> Fund:
    pl_str = row.get("VL_PATRIM_LIQ", "")
    try:
        pl = float(pl_str) if pl_str else None
    except ValueError:
        pl = None
    return Fund(
        cnpj=row.get("CNPJ_FUNDO", ""),
        nome=row.get("DENOM_SOCIAL", ""),
        classe=row.get("CLASSE", ""),
        situacao=row.get("SIT", ""),
        tipo=row.get("TP_FUNDO", ""),
        fundo_cotas=row.get("FUNDO_COTAS", ""),
        exclusivo=row.get("FUNDO_EXCLUSIVO", ""),
        patrimonio_liquido=pl,
        taxa_admin=row.get("TAXA_ADM", ""),
        gestor=row.get("GESTOR", ""),
        administrador=row.get("ADMIN", ""),
        classe_anbima=row.get("CLASSE_ANBIMA", ""),
    )


async def _load_catalog() -> list[Fund]:
    rows = await fetch_csv(FUND_CATALOG_URL)
    return [_parse_fund_row(row) for row in rows]


async def get_fund_catalog(
    only_active: bool = True,
    classe_filter: str | None = None,
) -> list[Fund]:
    """Fetch all registered investment funds from CVM.

    Args:
        only_active: Filter only active funds (SIT='EM FUNCIONAMENTO NORMAL').
        classe_filter: Filter by class (e.g., 'Fundo de Ações', 'FI-Infra').
    """
    funds = await _catalog_cache.get_or_load(_load_catalog)
    if only_active:
        funds = [f for f in funds if "FUNCIONAMENTO NORMAL" in f.situacao]
    if classe_filter:
        cf = classe_filter.upper()
        funds = [f for f in funds if cf in f.classe.upper()]
    return funds


def _parse_daily_row(row: dict[str, str]) -> FundDaily | None:
    cnpj = row.get("CNPJ_FUNDO_CLASSE") or row.get("CNPJ_FUNDO", "")
    try:
        return FundDaily(
            cnpj=cnpj,
            dt_comptc=row.get("DT_COMPTC", ""),
            vl_total=float(row.get("VL_TOTAL", "0") or "0"),
            vl_quota=float(row.get("VL_QUOTA", "0") or "0"),
            vl_patrimonio_liq=float(row.get("VL_PATRIM_LIQ", "0") or "0"),
            captacao_dia=float(row.get("CAPTC_DIA", "0") or "0"),
            resgate_dia=float(row.get("RESG_DIA", "0") or "0"),
            nr_cotistas=int(row.get("NR_COTST", "0") or "0"),
            tp_fundo_classe=row.get("TP_FUNDO_CLASSE", ""),
            id_subclasse=row.get("ID_SUBCLASSE", ""),
        )
    except (ValueError, KeyError):
        return None


async def get_fund_daily(
    year: int,
    month: int,
    cnpj_filter: str | None = None,
) -> list[FundDaily]:
    """Fetch daily fund data (NAV, quota, flows) for a given month.

    Args:
        year: Year (2021+).
        month: Month (1-12).
        cnpj_filter: Filter by fund CNPJ (highly recommended to reduce memory).
            Punctuated and digit-only forms both match.
    """
    ym = f"{year}{month:02d}"
    url = FUND_DAILY_URL.format(ym=ym)
    rows = await fetch_csv_from_zip(url)
    needle = cnpj_digits(cnpj_filter) if cnpj_filter else ""
    results: list[FundDaily] = []
    for row in rows:
        cnpj = row.get("CNPJ_FUNDO_CLASSE") or row.get("CNPJ_FUNDO", "")
        if needle and cnpj_digits(cnpj) != needle:
            continue
        parsed = _parse_daily_row(row)
        if parsed is not None:
            results.append(parsed)
    return results
