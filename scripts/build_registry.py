"""Offline regenerator for ``src/findata/data/registry.sqlite``.

Run me weekly (CI cron) or manually:

    python scripts/build_registry.py [--output PATH] [--skip-b3] [--only-active]

Pulls catalog data from CVM companies, CVM funds, and SUSEP, optionally
enriches CVM companies with B3 tickers via index-portfolio overlap, and
emits a single FTS5 SQLite file ready to ship inside the wheel.

This is the *only* source of truth for ``registry.sqlite`` — never edit
the file by hand. The CI workflow rebuilds and opens a PR if content
hash differs from the committed copy.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Repo paths — script lives at <repo>/scripts/build_registry.py
REPO = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO / "src" / "findata" / "registry" / "schema.sql"
DEFAULT_OUT = REPO / "src" / "findata" / "data" / "registry.sqlite"

# Make `findata` importable when run directly without `pip install -e .`
sys.path.insert(0, str(REPO / "src"))

from findata.sources.b3 import get_index_portfolio  # noqa: E402
from findata.sources.cvm import get_companies, get_fund_catalog  # noqa: E402
from findata.sources.susep import get_susep_empresas  # noqa: E402

# Indices fetched to harvest ticker → company-name pairs. The union covers
# essentially every liquid B3 listing. IBRA alone has ~180 names; the others
# pile on small caps, FIIs, dividend-yielders, and segmental indices.
B3_INDICES_FOR_TICKERS = ["IBRA", "IBXL", "IBOV", "SMLL", "IDIV", "IFIX"]


# ── Normalization ─────────────────────────────────────────────────


def normalize_name(s: str | None) -> str:
    """ASCII-fold + uppercase + collapse non-alphanumerics to single spaces.

    For NAMES (multi-word strings the user might search by). Punctuation like
    ``S.A.`` or ``& Cia`` becomes word separators, so individual words are
    independently matchable.

    ``"Itaú Unibanco S.A."`` → ``"ITAU UNIBANCO S A"``.
    """
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    upper = ascii_only.upper()
    out: list[str] = []
    last_was_space = True
    for c in upper:
        if c.isalnum():
            out.append(c)
            last_was_space = False
        elif not last_was_space:
            out.append(" ")
            last_was_space = True
    return "".join(out).strip()


def normalize_token(s: str | None) -> str:
    """ASCII-fold + uppercase, strip ALL non-alphanumerics (no spaces).

    For CODES (CNPJ, ticker, cod_cvm, codigo_fip) where we need the value to
    survive as ONE FTS5 token — splitting a CNPJ on its dots/slash would
    fragment it into pieces nobody can match exactly.

    ``"33.000.167/0001-01"`` → ``"33000167000101"``.
    """
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return "".join(c for c in ascii_only.upper() if c.isalnum())


def make_searchable(*, tokens: list[str | None], names: list[str | None]) -> str:
    """Build the FTS5 ``searchable`` payload for one entity.

    ``tokens`` are codes that must round-trip as single tokens (CNPJ,
    ticker, cod_cvm). ``names`` are human-readable labels that should be
    word-tokenized (nome_social, nome_comercial). Both lanes are joined
    by single spaces — the FTS5 tokenizer takes it from there.
    """
    parts: list[str] = []
    for t in tokens:
        n = normalize_token(t)
        if n:
            parts.append(n)
    for nm in names:
        n = normalize_name(nm)
        if n:
            parts.append(n)
    return " ".join(parts)


# ── B3 ticker enrichment (best-effort) ────────────────────────────


async def fetch_b3_ticker_map() -> dict[str, list[str]]:
    """Build ``{normalized_company_name: [tickers]}`` from B3 index portfolios.

    Best-effort: if any index fetch fails, we log and continue. Empty result
    just means companies won't get ticker enrichment — registry still works.
    """
    name_to_tickers: dict[str, list[str]] = {}
    for idx in B3_INDICES_FOR_TICKERS:
        try:
            portfolio = await get_index_portfolio(idx)
        except Exception as e:
            # Network is allowed to fail per-index — registry still builds without
            # ticker enrichment for the missing index. Log and move on.
            print(f"[warn] B3 {idx} fetch failed: {e}", file=sys.stderr)
            continue
        for c in portfolio.componentes:
            key = normalize_name(c.nome_ativo)
            if not key or not c.ticker:
                continue
            bucket = name_to_tickers.setdefault(key, [])
            if c.ticker not in bucket:
                bucket.append(c.ticker)
    return name_to_tickers


def b3_tickers_for_company(
    name_to_tickers: dict[str, list[str]],
    nome_comercial: str,
    nome_social: str,
) -> list[str]:
    """Look up tickers by normalized commercial name, fall back to social."""
    for candidate in (nome_comercial, nome_social):
        key = normalize_name(candidate)
        if key and key in name_to_tickers:
            return list(name_to_tickers[key])
    return []


# ── Per-source builders ───────────────────────────────────────────


async def build_cvm_companies(
    conn: sqlite3.Connection,
    name_to_tickers: dict[str, list[str]],
    only_active: bool,
) -> int:
    companies = await get_companies(only_active=only_active)
    rows: list[tuple[str, str]] = []
    for c in companies:
        tickers = b3_tickers_for_company(name_to_tickers, c.nome_comercial, c.nome_social)
        searchable = make_searchable(
            tokens=[c.cnpj, c.cod_cvm, *tickers],
            names=[c.nome_social, c.nome_comercial],
        )
        payload: dict[str, Any] = {
            "cnpj": c.cnpj,
            "nome": c.nome_comercial or c.nome_social,
            "kind": "cvm_company",
            "sources": ["cvm"] + (["b3"] if tickers else []),
            "tickers": tickers,
            "cod_cvm": c.cod_cvm,
            "extra": {
                "nome_social": c.nome_social,
                "nome_comercial": c.nome_comercial,
                "situacao": c.situacao,
                "setor": c.setor,
                "categoria": c.categoria,
                "controle_acionario": c.controle_acionario,
            },
        }
        rows.append((searchable, json.dumps(payload, ensure_ascii=False)))
    conn.executemany("INSERT INTO entities(searchable, payload) VALUES (?, ?)", rows)
    return len(rows)


async def build_cvm_funds(conn: sqlite3.Connection, only_active: bool) -> int:
    funds = await get_fund_catalog(only_active=only_active)
    rows: list[tuple[str, str]] = []
    for f in funds:
        searchable = make_searchable(tokens=[f.cnpj], names=[f.nome])
        payload: dict[str, Any] = {
            "cnpj": f.cnpj,
            "nome": f.nome,
            "kind": "cvm_fund",
            "sources": ["cvm"],
            "tickers": [],
            "extra": {
                "classe": f.classe,
                "tipo": f.tipo,
                "situacao": f.situacao,
                "fundo_cotas": f.fundo_cotas,
                "exclusivo": f.exclusivo,
                "patrimonio_liquido": f.patrimonio_liquido,
                "taxa_admin": f.taxa_admin,
                "gestor": f.gestor,
                "administrador": f.administrador,
                "classe_anbima": f.classe_anbima,
            },
        }
        rows.append((searchable, json.dumps(payload, ensure_ascii=False)))
    conn.executemany("INSERT INTO entities(searchable, payload) VALUES (?, ?)", rows)
    return len(rows)


async def build_susep(conn: sqlite3.Connection) -> int:
    empresas = await get_susep_empresas()
    rows: list[tuple[str, str]] = []
    for e in empresas:
        searchable = make_searchable(
            tokens=[e.cnpj, e.codigo_fip],
            names=[e.nome],
        )
        payload: dict[str, Any] = {
            "cnpj": e.cnpj,
            "nome": e.nome,
            "kind": "susep",
            "sources": ["susep"],
            "tickers": [],
            "codigo_fip": e.codigo_fip,
            "extra": {},
        }
        rows.append((searchable, json.dumps(payload, ensure_ascii=False)))
    conn.executemany("INSERT INTO entities(searchable, payload) VALUES (?, ?)", rows)
    return len(rows)


# ── Build orchestration ───────────────────────────────────────────


def open_fresh_db(path: Path) -> sqlite3.Connection:
    """Create an empty registry at ``path``, applying the canonical schema."""
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def write_meta(conn: sqlite3.Connection, source_counts: dict[str, int]) -> str:
    """Compute content hash + write build metadata. Returns the hash."""
    h = hashlib.sha256()
    for (payload,) in conn.execute("SELECT payload FROM entities ORDER BY rowid"):
        h.update(payload.encode("utf-8"))
    digest = h.hexdigest()
    meta_rows = [
        ("schema_version", "1"),
        ("built_at", datetime.now(UTC).isoformat(timespec="seconds")),
        ("sources_json", json.dumps(source_counts, sort_keys=True)),
        ("content_sha256", digest),
    ]
    conn.executemany("INSERT INTO meta(key, value) VALUES (?, ?)", meta_rows)
    return digest


def finalize(conn: sqlite3.Connection) -> None:
    """Compact the DB before closing — keeps shipped wheel size minimal."""
    conn.commit()
    # Drop the journal and compact pages so the file we ship is exactly
    # what fits the data, not whatever transient size SQLite preferred.
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.execute("VACUUM")
    conn.commit()


async def run(args: argparse.Namespace) -> int:
    print(f"[build_registry] output: {args.output}")
    conn = open_fresh_db(args.output)

    name_to_tickers: dict[str, list[str]] = {}
    if not args.skip_b3:
        print("[build_registry] fetching B3 index portfolios for ticker enrichment…")
        name_to_tickers = await fetch_b3_ticker_map()
        print(f"  → {len(name_to_tickers)} company names mapped to tickers")

    source_counts: dict[str, int] = {}

    print("[build_registry] CVM companies…")
    source_counts["cvm_companies"] = await build_cvm_companies(
        conn, name_to_tickers, only_active=args.only_active
    )
    print(f"  → {source_counts['cvm_companies']} rows")

    print("[build_registry] CVM funds…")
    source_counts["cvm_funds"] = await build_cvm_funds(conn, only_active=args.only_active)
    print(f"  → {source_counts['cvm_funds']} rows")

    print("[build_registry] SUSEP empresas…")
    source_counts["susep"] = await build_susep(conn)
    print(f"  → {source_counts['susep']} rows")

    digest = write_meta(conn, source_counts)
    finalize(conn)

    total = sum(source_counts.values())
    size_mb = args.output.stat().st_size / 1024 / 1024
    print(f"[build_registry] DONE: {total} entities, {size_mb:.2f} MB, sha256={digest[:16]}…")
    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output SQLite path (default: {DEFAULT_OUT.relative_to(REPO)})",
    )
    parser.add_argument(
        "--skip-b3",
        action="store_true",
        help="Skip B3 ticker enrichment (faster; useful for offline dev)",
    )
    parser.add_argument(
        "--only-active",
        action="store_true",
        help="Filter to active companies/funds only (smaller registry)",
    )
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
