"""Output contract for ``resolve_asset`` — the Wealthuman classification.

The resolver's job is to turn *any* asset identifier (ticker, CNPJ, ISIN, or
bare name) into a classification **already mapped to the Wealthuman macro
taxonomy**, not the raw CVM/ANBIMA category. Every field that can drive a
human-in-the-loop decision (``source``, ``confidence``, ``as_of``, ``cascade``)
is explicit, so a consolidated statement can be audited line by line.

Shapes mirror the spec in ``openfindata-mcp-spec.md`` §Output. Kept in lockstep
with the engine in :mod:`findata.resolver.engine`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ── Controlled vocabularies ────────────────────────────────────────

# Veículo / instrumento. Mirrors the spec's ``kind`` enum.
Kind = Literal[
    "fundo",
    "acao",
    "fii",
    "etf",
    "bdr",
    "debenture",
    "cra",
    "cri",
    "cdb",
    "lci_lca",
    "tesouro",
    "coe",
    "outro",
]

# Wealthuman macro taxonomy — PURE asset class. Geography is NOT a macro value:
# "Internacional" lives only on the orthogonal ``Exposure`` axis. So an offshore
# equity fund is RV + exposure=Internacional, offshore debt is RF + Internacional.
# ``Indefinido`` is the honest answer when no layer can decide (drives HITL review).
MacroClass = Literal[
    "Renda Fixa",
    "Renda Variável",
    "Multimercado",
    "Alternativos",
    "Estruturados",
    "Indefinido",
]

# Geography/strategy axis — *where the economic exposure sits*, orthogonal to
# the asset class. A B3-listed equity ETF on the S&P 500 (IVVB11) is RV by class
# but Internacional by exposure; a BDR is RV but the holder bears USD/foreign
# risk → Internacional. The B3 listing is only the asset's domicile, not its
# exposure. ``None`` when the resolver cannot decide.
Exposure = Literal["Brasil", "Internacional"]

# Economic nature of the underlying. For ETFs/funds this is what splits an
# ETF-de-ações (RV) from an ETF-de-debêntures (RF) — see IFRA11 vs IVVB11.
UnderlyingNature = Literal[
    "acoes",
    "debentures",
    "credito",
    "recebiveis",
    "imoveis",
    "multiativos",
    "tesouro",
    "cambio",
    "private_equity",
    "outro",
]


class IdentifierResolved(BaseModel):
    """The identifiers the resolver could normalize/confirm from the input."""

    cnpj: str | None = None
    ticker: str | None = None
    isin: str | None = None
    name: str | None = None


class CvmInfo(BaseModel):
    """Raw upstream classification, kept for audit alongside the mapped macro."""

    classe: str | None = None
    anbima_categoria: str | None = None
    estrutura: str | None = None  # FIA | FIM | FIC | FIDC | FIP | FII | IE | ETF | ...


class DebentureInfo(BaseModel):
    """Debenture-specific facts. Only populated when ``kind == 'debenture'``
    (or an FI-Infra ETF whose underlying *is* incentivada debentures)."""

    incentivada_1243: bool | None = None  # Lei 12.431 (infra) — IR-exempt for PF
    indexador: str | None = None  # IPCA+ | CDI+ | %CDI | PREFIXADO | SELIC
    vencimento: str | None = None  # YYYY-MM when known


class TaxInfo(BaseModel):
    """Tax treatment for the typical PF holder."""

    isento: bool | None = None  # True for Lei 12.431 / LCI-LCA / FII dividends etc.


class AssetClassification(BaseModel):
    """The full resolver output. One asset in → one auditable record out."""

    identifier_resolved: IdentifierResolved
    kind: Kind
    cvm: CvmInfo = Field(default_factory=CvmInfo)
    macro_class: MacroClass
    subclasse: str | None = None
    exposure: Exposure | None = None  # geography/strategy axis (Brasil vs Internacional)
    underlying_nature: UnderlyingNature | None = None
    debenture: DebentureInfo | None = None
    tax: TaxInfo = Field(default_factory=TaxInfo)
    source: str  # openfindata | maisretorno | cvm | b3 | web_search
    confidence: float = Field(ge=0.0, le=1.0)
    as_of: str  # YYYY-MM-DD
    # Audit trail: ordered list of resolution steps actually attempted.
    cascade: list[str] = Field(default_factory=list)
    # Free-text rationale, e.g. which trap was avoided or which signal decided.
    notes: str | None = None
