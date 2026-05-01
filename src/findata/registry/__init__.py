"""Dados Financeiros Abertos registry — flat FTS5 catalog of CNPJ-keyed entities.

Embedded in the wheel at ``src/findata/data/registry.sqlite`` (built offline by
``scripts/build_registry.py``, refreshed weekly by CI). One ``MATCH`` query
handles exact CNPJ/ticker/cod_cvm/FIP code lookups, prefix searches, and
fuzzy name searches — the BM25 rank tells you which kind you got.
"""

from findata.registry.models import Entity, LookupResult
from findata.registry.store import get_meta, lookup

__all__ = ["Entity", "LookupResult", "get_meta", "lookup"]
