"""CVM CDA — Composição e Diversificação da Carteira (fund holdings).

The CDA monthly zip is huge (~150 MB unzipped across 12 CSVs split by
asset class — `BLC_1` through `BLC_8` plus confidential, PL summary, and
FIE blocks). Scanning everything per call would burn RAM and CPU, so we
**always require a CNPJ filter**. The zip itself is cached once per
period via the LRU client; we line-stream every CSV inside it looking
for matching rows.

Block layout (observed 2026):

| Block       | Asset class                                          |
|-------------|------------------------------------------------------|
| BLC_1       | Títulos públicos federais                            |
| BLC_2       | Cotas de fundos                                      |
| BLC_3       | Swaps / derivativos OTC                              |
| BLC_4       | Ações / debêntures                                   |
| BLC_5       | Depósitos a prazo / CDB / títulos de IF              |
| BLC_6       | CRA / agronegócio (debêntures + securitizadas)       |
| BLC_7       | Investimento no exterior                             |
| BLC_8       | Disponibilidades / valores a pagar / outros          |
| CONFID      | Posições sob sigilo                                  |
| PL          | Resumo do patrimônio líquido                         |
| fie         | Fundos de Investimento no Exterior (FIE)             |
| fie_CONFID  | FIE sob sigilo                                       |
"""

from __future__ import annotations

import csv
import io
import re
import sys
import zipfile

from pydantic import BaseModel

from findata.http_client import get_bytes
from findata.sources.cvm._directory import CVM_BASE

# CDA rows occasionally pack long free-text descriptions that overflow the
# default 128 KiB csv field limit. Bump it once at import.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

CDA_URL = f"{CVM_BASE}/FI/DOC/CDA/DADOS/cda_fi_{{ym}}.zip"

_NON_DIGIT = re.compile(r"\D")


def _digits(value: str | None) -> str:
    """Strip a CNPJ down to its digits so punctuated and bare forms compare equal."""
    return _NON_DIGIT.sub("", value or "")


class FundHolding(BaseModel):
    """One holding row (one asset position) inside one fund's portfolio."""

    cnpj: str
    nome_fundo: str
    dt_referencia: str  # YYYY-MM-DD
    bloco: str  # 'BLC_1'..'BLC_8' or 'CONFID' / 'PL' / 'FIE'
    tipo_aplicacao: str | None = None  # TP_APLIC — broad asset class
    tipo_ativo: str | None = None  # TP_ATIVO — specific asset type
    emissor: str | None = None  # EMISSOR / EMISSOR_LIGADO
    cnpj_emissor: str | None = None  # CNPJ_EMISSOR (when present)
    tipo_negociacao: str | None = None  # TP_NEGOC
    quantidade_final: float | None = None  # QT_POS_FINAL
    valor_mercado: float | None = None  # VL_MERC_POS_FINAL
    descricao: str | None = None  # DS_ATIVO / free-text label
    raw: dict[str, str] | None = None  # full original row when caller wants it


def _f(val: str | None) -> float | None:
    if val is None or not val.strip() or val.strip() in {"--", "N/D"}:
        return None
    try:
        return float(val.replace(",", "."))
    except ValueError:
        return None


_BLC_PARTS_MIN = 4  # parts[2] must be at index 2, so we need >=4 parts


def _block_label(filename: str) -> str:
    """Extract 'BLC_4' / 'CONFID' / 'PL' / 'fie' from a CSV filename."""
    base = filename.split("/")[-1]
    parts = base.replace(".csv", "").split("_")
    # cda_fi_BLC_4_202603 → BLC_4
    # cda_fi_CONFID_202603 → CONFID
    # cda_fi_PL_202603 → PL
    # cda_fie_202603 → FIE
    if len(parts) >= _BLC_PARTS_MIN and parts[2] == "BLC":
        return f"BLC_{parts[3]}"
    if "CONFID" in base.upper():
        return "FIE_CONFID" if "fie" in base.lower() else "CONFID"
    if base.startswith("cda_fie"):
        return "FIE"
    if "_PL_" in base.upper():
        return "PL"
    return "OTHER"


def _row_to_holding(row: dict[str, str], block: str, *, include_raw: bool) -> FundHolding | None:
    cnpj = (row.get("CNPJ_FUNDO_CLASSE") or row.get("CNPJ_FUNDO", "")).strip()
    if not cnpj:
        return None
    nome = (row.get("DENOM_SOCIAL") or row.get("DENOM_CLASSE", "")).strip()
    dt = (row.get("DT_COMPTC") or "").strip()
    return FundHolding(
        cnpj=cnpj,
        nome_fundo=nome,
        dt_referencia=dt,
        bloco=block,
        tipo_aplicacao=row.get("TP_APLIC") or None,
        tipo_ativo=row.get("TP_ATIVO") or None,
        emissor=(row.get("EMISSOR_LIGADO") or row.get("EMISSOR") or None),
        cnpj_emissor=row.get("CNPJ_EMISSOR") or row.get("CPF_CNPJ_EMISSOR") or None,
        tipo_negociacao=row.get("TP_NEGOC") or None,
        quantidade_final=_f(row.get("QT_POS_FINAL")),
        valor_mercado=_f(
            row.get("VL_MERC_POS_FINAL") or row.get("VL_MERCADO") or row.get("VL_MERC_POSICAO")
        ),
        descricao=(row.get("DS_ATIVO") or row.get("CD_ATIVO") or None),
        raw=row if include_raw else None,
    )


async def get_fund_holdings(
    cnpj: str,
    year: int,
    month: int,
    blocks: list[str] | None = None,
    include_raw: bool = False,
) -> list[FundHolding]:
    """Every position held by ``cnpj`` on the last business day of ``year/month``.

    Args:
        cnpj: Fund CNPJ. Required — there are tens of thousands of funds and
            scanning all blocks for everyone is RAM-prohibitive.
        year, month: Reference period (CVM publishes once per month).
        blocks: Optional whitelist (e.g. ``['BLC_1','BLC_4']`` to only fetch
            government bonds + equities). ``None`` → every block.
        include_raw: When ``True``, the parsed model carries the original
            CSV row in ``raw`` so callers can access block-specific fields
            we don't model explicitly.
    """
    ym = f"{year}{month:02d}"
    raw = await get_bytes(CDA_URL.format(ym=ym), cache_ttl=86400)
    cnpj_norm = _digits(cnpj)
    wanted_blocks = {b.upper() for b in blocks} if blocks else None
    holdings: list[FundHolding] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for entry in zf.namelist():
            if not entry.endswith(".csv"):
                continue
            block = _block_label(entry)
            if wanted_blocks is not None and block not in wanted_blocks:
                continue
            with zf.open(entry) as f:
                reader = csv.DictReader(io.StringIO(f.read().decode("iso-8859-1")), delimiter=";")
                for row in reader:
                    row_cnpj = _digits(row.get("CNPJ_FUNDO_CLASSE") or row.get("CNPJ_FUNDO"))
                    if row_cnpj != cnpj_norm:
                        continue
                    h = _row_to_holding(row, block, include_raw=include_raw)
                    if h is not None:
                        holdings.append(h)
    return holdings
