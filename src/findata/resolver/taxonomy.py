"""CVM/ANBIMA → Wealthuman macro mapping.

The spec is explicit (§Regras-chave #1): *the* mapping from the raw CVM class /
ANBIMA category to the Wealthuman macro taxonomy lives **in the resolver**, not
in the caller. This module is that mapping, kept as plain data so it is
auditable and easy to extend when ANBIMA renames a category.

It is consulted by the registry-enrichment step of the cascade, when we have a
CVM ``classe`` / ``CLASSE_ANBIMA`` string but the structural rules in
:mod:`findata.resolver.engine` did not already settle the macro from the name.
"""

from __future__ import annotations

from findata.resolver.normalize import fold

# ── CVM legal class (campo CLASSE do cad_fi) → macro (asset class) ──
# The CVM "classe" is the legal/regulatory bucket. macro is PURE asset class;
# geography (Internacional) is a separate axis — so "Fundo de Dívida Externa" is
# Renda Fixa here, with its Internacional exposure set by the exposure map below.
CVM_CLASSE_TO_MACRO: dict[str, str] = {
    "FUNDO DE ACOES": "Renda Variável",
    "FUNDO DE RENDA FIXA": "Renda Fixa",
    "FUNDO MULTIMERCADO": "Multimercado",
    "FUNDO CAMBIAL": "Multimercado",  # câmbio puro — banker treats as Multi/Alt
    "FUNDO DE CURTO PRAZO": "Renda Fixa",
    "FUNDO REFERENCIADO": "Renda Fixa",
    "FUNDO DE DIVIDA EXTERNA": "Renda Fixa",  # asset class RF; exposure Internacional
    # FI-Infra (debêntures incentivadas) — RF by underlying.
    "FI-INFRA": "Renda Fixa",
    "FIC FI-INFRA": "Renda Fixa",
}

# ── ANBIMA category (CLASSE_ANBIMA) → macro (asset class) ──────────
# Richer than the legal class: the ANBIMA category encodes the mandate. Matched
# by substring on the folded string. macro is the asset class only — the
# "investimento no exterior" / "dívida externa" mandate feeds the EXPOSURE map,
# not macro, so an "Ações Investimento no Exterior" is RV + Internacional.
ANBIMA_SUBSTRING_TO_MACRO: tuple[tuple[str, str], ...] = (
    # Core asset classes (geography handled separately).
    ("DIVIDA EXTERNA", "Renda Fixa"),
    ("RENDA FIXA", "Renda Fixa"),
    ("ACOES", "Renda Variável"),
    ("MULTIMERCADO", "Multimercado"),
    ("CAMBIAL", "Multimercado"),
    # Structured / private-market vehicles.
    ("FIP", "Alternativos"),
    ("PRIVATE EQUITY", "Alternativos"),
    ("FIDC", "Renda Fixa"),  # direitos creditórios — credit nature → RF
    ("IMOBILIARIO", "Renda Variável"),  # FII
)

# Substrings in a CVM/ANBIMA category that mark Internacional exposure.
_INTERNACIONAL_MARKERS: tuple[str, ...] = (
    "INVESTIMENTO NO EXTERIOR",
    "DIVIDA EXTERNA",
    "EXTERIOR",
    "GLOBAL",
)


def map_cvm_classe(classe: str | None) -> str | None:
    """Map a raw CVM legal ``CLASSE`` to a Wealthuman macro (asset class), or ``None``."""
    if not classe:
        return None
    return CVM_CLASSE_TO_MACRO.get(fold(classe))


def map_anbima_categoria(categoria: str | None) -> str | None:
    """Map a raw ANBIMA category to a Wealthuman macro by first-match substring."""
    if not categoria:
        return None
    folded = fold(categoria)
    for needle, macro in ANBIMA_SUBSTRING_TO_MACRO:
        if needle in folded:
            return macro
    return None


def map_exposure(categoria: str | None) -> str | None:
    """Detect Internacional exposure from a CVM/ANBIMA category, else ``None``."""
    if not categoria:
        return None
    folded = fold(categoria)
    return "Internacional" if any(m in folded for m in _INTERNACIONAL_MARKERS) else None
