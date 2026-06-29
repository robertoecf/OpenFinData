"""Identifier normalization for the resolver.

Turns the loose input (``{name, cnpj, ticker, isin}`` — any subset) into a
canonical :class:`NormalizedInput` the rule engine can pattern-match against:
folded/uppercased name tokens, a digits-only CNPJ, an uppercased ticker, and an
ISIN. Pure, deterministic, no I/O — so it is trivially cacheable.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# A B3 ticker: 4 letters + 1-2 digits (PETR4, IVVB11, HGLG11). Fractional and
# subscription receipts (F, suffixes) are out of scope for classification.
_TICKER_RE = re.compile(r"^[A-Z]{4}\d{1,2}$")
# BDR: 4 letters + 34/35 (level I / level II). e.g. AAPL34, MSFT34.
_BDR_RE = re.compile(r"^[A-Z]{4}3[45]$")
# ISIN: 2-letter country + 9 alnum + 1 check digit. Brazil = BR....
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
_CNPJ_LEN = 14


def fold(text: str) -> str:
    """ASCII-fold + uppercase, the canonical form for keyword matching.

    ``"Crédito Estruturado"`` → ``"CREDITO ESTRUTURADO"``. Mirrors how the
    registry stores tokens, so comparisons line up.
    """
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_only.upper().strip()


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def tokenize(name: str) -> list[str]:
    """Split a folded name into alphanumeric tokens (keeps ``+`` joined runs out).

    ``"DEB PETROBRAS IPCA+"`` → ``["DEB", "PETROBRAS", "IPCA"]``. The ``+`` is
    dropped from tokens but preserved in the raw folded name, which the indexador
    parser reads, so ``IPCA+`` is still recoverable.
    """
    return [t for t in re.split(r"[^A-Z0-9]+", fold(name)) if t]


@dataclass(frozen=True)
class NormalizedInput:
    """Canonical, deterministic view of the caller's identifiers."""

    name_raw: str | None = None  # original, for echo-back
    name_folded: str = ""  # ASCII-folded + uppercased full string
    tokens: tuple[str, ...] = field(default_factory=tuple)
    cnpj: str | None = None  # 14 digits, or None
    ticker: str | None = None  # uppercased B3 ticker, or None
    isin: str | None = None

    def has_token(self, *candidates: str) -> bool:
        """True if any candidate appears as a whole token."""
        tset = set(self.tokens)
        return any(c in tset for c in candidates)

    def name_contains(self, *needles: str) -> bool:
        """True if any needle is a substring of the folded name (phrase match)."""
        return any(n in self.name_folded for n in needles)

    @property
    def ticker_digits_suffix(self) -> str | None:
        """The trailing digits of the ticker (``"11"`` for HGLG11), or None."""
        if not self.ticker:
            return None
        m = re.search(r"(\d{1,2})$", self.ticker)
        return m.group(1) if m else None


def normalize(
    *,
    name: str | None = None,
    cnpj: str | None = None,
    ticker: str | None = None,
    isin: str | None = None,
) -> NormalizedInput:
    """Build a :class:`NormalizedInput` from any subset of identifiers.

    A bare ``name`` that is itself a ticker/CNPJ/ISIN is promoted to the right
    field, so callers can pass a single opaque string and still get structured
    signals (the consolidator often only has the statement label).
    """
    # Promote a bare identifier passed as `name` into its typed slot.
    if name and not (ticker or cnpj or isin):
        candidate = fold(name)
        if _TICKER_RE.match(candidate) or _BDR_RE.match(candidate):
            ticker = candidate
        elif _ISIN_RE.match(candidate):
            isin = candidate
        elif len(_digits(name)) == _CNPJ_LEN and not re.search(r"[A-Za-z]", name):
            cnpj = name

    cnpj_norm = None
    if cnpj:
        d = _digits(cnpj)
        cnpj_norm = d if len(d) == _CNPJ_LEN else None

    ticker_norm = None
    if ticker:
        t = fold(ticker)
        ticker_norm = t if (_TICKER_RE.match(t) or _BDR_RE.match(t)) else None

    isin_norm = None
    if isin:
        i = fold(isin)
        isin_norm = i if _ISIN_RE.match(i) else None

    folded = fold(name) if name else ""
    return NormalizedInput(
        name_raw=name,
        name_folded=folded,
        tokens=tuple(tokenize(name)) if name else (),
        cnpj=cnpj_norm,
        ticker=ticker_norm,
        isin=isin_norm,
    )
