"""Wealthuman asset-classification resolver.

``resolve_asset(identifier)`` turns any Brazilian asset identifier (ticker,
CNPJ, ISIN, or bare name) into a classification already mapped to the Wealthuman
macro taxonomy (Renda Fixa, Renda Variável, Multimercado, Internacional,
Alternativos, Estruturados) plus subclasse, underlying nature, debenture /
Lei-12.431 facts, source, confidence, and an audit cascade.

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
