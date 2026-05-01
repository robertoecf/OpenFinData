"""Read-only async store over the embedded FTS5 ``registry.sqlite``.

One ``MATCH`` query handles exact-token (CNPJ, ticker, cod_cvm, FIP code)
and fuzzy-name lookups uniformly. The BM25 rank tells the caller which
kind they got — see :class:`findata.registry.models.Entity` for the
empirical rank buckets.

The SQLite file ships embedded inside the wheel at
``findata/data/registry.sqlite``. ``REGISTRY_PATH`` resolves it
relative to this module so tests can monkey-patch it to a fixture file.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import aiosqlite

from findata.registry.models import Entity, LookupResult

# Resolved at import time — but importable code can override before the first
# query (tests do this). The path layout reflects:
#   src/findata/registry/store.py   ← __file__
#   src/findata/data/registry.sqlite
REGISTRY_PATH: Path = Path(__file__).resolve().parent.parent / "data" / "registry.sqlite"

_MIN_QUERY_LEN = 2

# Tokens FTS5 interpreta como operadores se aparecerem fora de aspas. Quando
# um usuário digita literalmente ``OR``, ``AND``, etc., precisamos quotar
# pra (a) não derrubar o índice com syntax error e (b) não deixar o usuário
# injetar booleanos no parser.
_FTS5_RESERVED = frozenset({"AND", "OR", "NOT", "NEAR"})


def _escape_token(t: str) -> str:
    """Make one token safe for FTS5 MATCH and prefix-aware.

    * Reserved words (``AND``/``OR``/``NOT``/``NEAR``) get phrase-quoted so
      FTS5 treats them as literals — otherwise the query crashes with a
      ``syntax error`` (DoS via public endpoint) or, worse, returns
      attacker-controlled results (FTS injection).
    * Other tokens get a ``*`` suffix for prefix matching: ``PETROBR*``
      finds ``PETROBRAS``, ``33000167000101*`` matches the exact CNPJ
      token (and only that one, since prefix is unique here).
    """
    if t in _FTS5_RESERVED:
        return f'"{t}"'
    return f"{t}*"


def _normalize_query(q: str) -> str:
    """Turn a user query into FTS5 MATCH-ready text.

    Three variants are OR'd together so a single MATCH covers exact codes,
    multi-word names, prefix searches, AND inputs the user typed with a
    label (``"CNPJ: 33..."``):

    * **spaced**: tokens AND'd with implicit conjunction; each token is
      escaped via :func:`_escape_token` (prefix wildcard or quoted reserved).
      Handles multi-word names like ``"banco do brasil"`` and pure-prefix
      searches like ``"PETROBR"``.
    * **joined**: all tokens concatenated then prefix-escaped. Recovers
      codes typed with punctuation: ``"33.000.167/0001-01"`` → joined
      ``"33000167000101"`` → matches the canonical CNPJ token.
    * **digits-only joined**: same idea but only digit-only tokens are
      kept before joining. Rescues ``"CNPJ: 33.000.167/0001-01"`` where
      the alpha label ``CNPJ`` would otherwise contaminate the joined
      form into ``"CNPJ33000167000101"`` (no such token exists).

    Branches that produce no hit cost nothing; the matching branch wins
    on BM25 rank. Tokens are ASCII-folded + uppercased first because
    registry tokens are stored that way at build time.

    Returns ``""`` for queries shorter than ``_MIN_QUERY_LEN`` chars or
    with no alphanumeric content — caller treats as "no useful query".
    """
    if not q or len(q.strip()) < _MIN_QUERY_LEN:
        return ""
    nfkd = unicodedata.normalize("NFKD", q)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    upper = ascii_only.upper()
    tokens = [t for t in re.split(r"[^A-Z0-9]+", upper) if t]
    if not tokens:
        return ""

    spaced = " ".join(_escape_token(t) for t in tokens)
    joined = "".join(tokens)
    digits_joined = "".join(t for t in tokens if t.isdigit())

    # Build distinct variants — order doesn't matter for FTS5 OR semantics.
    variants: list[str] = [spaced]
    if joined != tokens[0] or len(tokens) > 1:
        je = _escape_token(joined)
        if je not in variants:
            variants.append(je)
    if digits_joined and digits_joined != joined:
        dje = _escape_token(digits_joined)
        if dje not in variants:
            variants.append(dje)

    if len(variants) == 1:
        return variants[0]
    return " OR ".join(f"({v})" for v in variants)


def _row_to_entity(row: aiosqlite.Row) -> Entity:
    """Decode one FTS5 row into an :class:`Entity` with rank attached."""
    payload = json.loads(row["payload"])
    payload["rank"] = row["rank"]
    return Entity(**payload)


async def lookup(query: str, limit: int = 20) -> LookupResult:
    """Resolve ``query`` against the registry, ordered by FTS5 BM25 rank.

    Args:
        query: user input — CNPJ (with or without mask), B3 ticker
            (PETR4, ITUB4), CVM code (9512), SUSEP FIP code, or a name
            fragment (substring of nome_social or nome_comercial).
        limit: cap on returned entities (default 20).

    Returns an empty result for queries shorter than 2 chars or with no
    alphanumeric content. Never raises for "no match" — empty list is
    the honest answer.
    """
    fts = _normalize_query(query)
    if not fts:
        return LookupResult(query=query, entities=[], total=0)

    async with aiosqlite.connect(str(REGISTRY_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT rank, payload FROM entities WHERE searchable MATCH ? ORDER BY rank LIMIT ?",
            (fts, limit),
        )
        rows = await cursor.fetchall()

    entities = [_row_to_entity(r) for r in rows]
    return LookupResult(query=query, entities=entities, total=len(entities))


async def get_meta() -> dict[str, str]:
    """Return the build metadata KV table — useful for /healthz and CI."""
    async with aiosqlite.connect(str(REGISTRY_PATH)) as db:
        cursor = await db.execute("SELECT key, value FROM meta")
        rows = await cursor.fetchall()
    meta: dict[str, str] = {}
    for key, value in rows:
        meta[key] = value
    return meta
