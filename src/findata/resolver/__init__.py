"""Asset-classification resolver.

``resolve_asset(identifier)`` turns any Brazilian asset identifier (ticker,
CNPJ, ISIN, or bare name) into a classification mapped to a macro allocation
taxonomy: ``macro_class`` is the asset class (Renda Fixa, Renda Variável,
Multimercado, Alternativos, Estruturados); geography is the orthogonal
``exposure`` axis (Brasil/Internacional). Plus subclasse, underlying nature,
debenture / Lei-12.431 facts (with a certainty status), source, confidence, an
audit cascade, and structured signals.

Deterministic, cacheable, auditable, no PII. See ``openfindata-mcp-spec.md``.
"""

from __future__ import annotations

from findata.resolver.engine import AssetProvider, classify, resolve_asset
from findata.resolver.models import (
    AssetClassification,
    CvmInfo,
    DebentureInfo,
    IdentifierResolved,
    TaxInfo,
)
from findata.resolver.normalize import NormalizedInput, normalize

__all__ = [
    "AssetClassification",
    "AssetProvider",
    "CvmInfo",
    "DebentureInfo",
    "IdentifierResolved",
    "NormalizedInput",
    "TaxInfo",
    "classify",
    "normalize",
    "resolve_asset",
]
