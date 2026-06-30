"""Curated knowledge base for classifications that are *not derivable* from the
identifier alone.

Two honest cases need a curated table, and only these:

1. **ETFs** — an ETF's macro follows its *underlying*, and the ticker carries no
   underlying signal. ``IVVB11`` (S&P 500 equities → RV) and ``IFRA11``
   (infra debentures → RF) both end in ``11``; nothing in the symbol separates
   them. The B3 ETF universe is small (~100 listed) and stable, so a curated
   ticker→underlying map is the deterministic, auditable answer.
2. **Global-mandate funds with no structural tell** — ``ARBOR FIC FIA`` is an
   equities wrapper (FIA → RV) whose mandate is global, but the name has no
   ``IE`` and no "global"/"world" keyword. Only fund-level knowledge sets its
   exposure=Internacional (economic nature beats the wrapper); the asset class
   stays Renda Variável.

Everything else is settled by the structural rules in
:mod:`findata.resolver.engine` and never reaches this table. Keep this list
small and sourced — it is a maintenance liability, not a dumping ground.

``confidence`` here is intentionally high (curated, manually verified) but < 1.0:
the underlying universe can change (an ETF can be delisted, a fund can change
mandate), so a curated hit is strong, not infallible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from findata.resolver.normalize import fold


@dataclass(frozen=True)
class SeedEntry:
    """One curated classification, matched by ticker / CNPJ / name substrings."""

    payload: dict[str, Any]
    ticker: str | None = None
    cnpj: str | None = None
    name_substrings: tuple[str, ...] = field(default_factory=tuple)


# ── B3 ETFs: ticker → (index, exposure) ────────────────────────────
# RV ETFs (equity underlying). macro is always Renda Variável (asset class);
# the geography is the orthogonal *exposure* axis. IVVB11 is the spec case: it
# is RV by class but its exposure is Internacional (tracks the S&P 500) — the B3
# listing is only the asset's domicile, not where the risk sits.
_EQUITY_ETFS = {
    # Brazilian-equity exposure.
    "BOVA11": ("Ibovespa", "Brasil"),
    "SMAL11": ("Small Caps", "Brasil"),
    "BOVV11": ("Ibovespa", "Brasil"),
    "PIBB11": ("IBrX-50", "Brasil"),
    "DIVO11": ("Dividendos", "Brasil"),
    "BOVB11": ("Ibovespa", "Brasil"),
    # International-equity exposure (B3-listed, foreign underlying).
    "IVVB11": ("S&P 500", "Internacional"),
    "XINA11": ("China (MSCI)", "Internacional"),
    "NASD11": ("Nasdaq-100", "Internacional"),
    "SPXI11": ("S&P 500", "Internacional"),
    "EURP11": ("Europa", "Internacional"),
    "ACWI11": ("Global (ACWI)", "Internacional"),
}

# RF ETFs (fixed-income underlying). IFRA11 is the headline case: an FI-Infra
# ETF holding Lei-12.431 infra debentures → Renda Fixa, IR-exempt for PF.
_FIXED_INCOME_ETFS = {
    "IFRA11": ("debentures", "Indexada à Inflação", True),
    "IB5M11": ("tesouro", "Indexada à Inflação", False),
    "IMAB11": ("tesouro", "Indexada à Inflação", False),
    "B5P211": ("tesouro", "Indexada à Inflação", False),
    "IRFM11": ("tesouro", "Prefixada", False),
    "FIXA11": ("tesouro", "Prefixada", False),
    "LFTS11": ("tesouro", "Pós-fixada", False),
    "B5MB11": ("tesouro", "Indexada à Inflação", False),
}


def _build_etf_seed() -> list[SeedEntry]:
    entries: list[SeedEntry] = []
    for ticker, (idx, exposure) in _EQUITY_ETFS.items():
        intl = exposure == "Internacional"
        entries.append(
            SeedEntry(
                ticker=ticker,
                payload={
                    "kind": "etf",
                    "macro_class": "Renda Variável",
                    "subclasse": "ETF de ações internacional" if intl else "ETF de ações",
                    "exposure": exposure,
                    "underlying_nature": "acoes",
                    "estrutura": "ETF",
                    "notes": f"Curated: ETF de ações ({idx}); classe RV, exposição {exposure}.",
                    "confidence": 0.97,
                },
            )
        )
    for ticker, (underlying, subclasse, incentivada) in _FIXED_INCOME_ETFS.items():
        note = "ETF de renda fixa; classifica pelo underlying (→ RF)."
        if incentivada:
            note = (
                "ETF de debêntures de infraestrutura (FI-Infra, Lei 12.431); "
                "underlying = debêntures incentivadas → RF, isento p/ PF."
            )
        payload = {
            "kind": "etf",
            "macro_class": "Renda Fixa",
            "subclasse": subclasse,
            "exposure": "Brasil",
            "underlying_nature": underlying,
            "estrutura": "ETF",
            "notes": f"Curated: {note}",
            "confidence": 0.97,
        }
        if incentivada:
            payload["debenture"] = {
                "incentivada_1243": True,
                "lei_12431_status": "confirmed",
                "indexador": "IPCA+",
            }
            payload["tax"] = {"isento": True, "isento_status": "confirmed_exempt"}
        # Tesouro-backed RF ETFs hold no debenture, so `debenture` stays None
        # (the honest "no debenture facts" shape) rather than a stub object.
        entries.append(SeedEntry(ticker=ticker, payload=payload))
    return entries


# ── Global-mandate funds with no structural tell ───────────────────
_GLOBAL_FUNDS = [
    SeedEntry(
        # Require both the brand token AND the FIA structure so an unrelated
        # "ARBOR Crédito Privado FIM" is NOT swept into the global-equity seed.
        name_substrings=("ARBOR", "FIA"),
        payload={
            "kind": "fundo",
            "macro_class": "Renda Variável",
            "subclasse": "Ações Global",
            "exposure": "Internacional",
            "underlying_nature": "acoes",
            "estrutura": "FIA",
            "notes": (
                "Curated: FIC FIA de mandato global sem sufixo IE; classe RV "
                "(ações), exposição Internacional pela natureza econômica."
            ),
            "confidence": 0.93,
        },
    ),
]


SEED_ENTRIES: list[SeedEntry] = _build_etf_seed() + _GLOBAL_FUNDS

# Index by ticker for O(1) hits (the common path).
_BY_TICKER: dict[str, SeedEntry] = {e.ticker: e for e in SEED_ENTRIES if e.ticker}
_BY_CNPJ: dict[str, SeedEntry] = {e.cnpj: e for e in SEED_ENTRIES if e.cnpj}
_NAME_ENTRIES: list[SeedEntry] = [e for e in SEED_ENTRIES if e.name_substrings]


def lookup_seed(*, ticker: str | None, cnpj: str | None, name_folded: str) -> SeedEntry | None:
    """Return the curated entry for this identifier, or ``None``.

    Ticker and CNPJ are exact; name match requires every configured substring to
    be present in the folded name (so ``("ARBOR",)`` matches "ARBOR FIC FIA").
    """
    if ticker and ticker in _BY_TICKER:
        return _BY_TICKER[ticker]
    if cnpj and cnpj in _BY_CNPJ:
        return _BY_CNPJ[cnpj]
    if name_folded:
        folded = fold(name_folded)
        for entry in _NAME_ENTRIES:
            if all(sub in folded for sub in entry.name_substrings):
                return entry
    return None
