-- Dados Financeiros Abertos registry — flat FTS5 catalog of CNPJ-keyed entities.
--
-- Design choice (Sprint 5): one virtual table, no separate keys/lookup tables.
-- Tokenization (unicode61 + remove_diacritics) treats sequences of alphanumerics
-- as single tokens, so:
--   "33000167000101"  → one token (matches exact CNPJ)
--   "PETR4"           → one token (matches exact ticker)
--   "petrobras"       → one token (matches names containing it; BM25 ranks)
--   "banco do brasil" → 3 tokens, FTS5 does an implicit AND
-- A single MATCH query handles exact, partial, and fuzzy lookups uniformly.
-- BM25 rank discriminates exact-match-on-unique-token (very negative rank)
-- from broader name matches (less negative).
--
-- Built offline by scripts/build_registry.py and shipped inside the wheel
-- (committed at src/findata/data/registry.sqlite). No runtime ETL.

CREATE VIRTUAL TABLE entities USING fts5(
    -- Searchable: space-separated normalized keys + name aliases for an entity.
    -- Examples of the constructed string:
    --   "33000167000101 PETR3 PETR4 9512 PETROBRAS PETROLEO BRASILEIRO S A"
    --   "07628528000159 PETR3F 18112 PETROBRAS DISTRIBUIDORA SA BR"
    -- Build script is responsible for normalization (UPPER, strip punctuation,
    -- ASCII-fold). FTS5's tokenizer further removes diacritics at index time.
    searchable,

    -- Opaque payload: JSON blob with the unified entity profile.
    -- Stored as-is (UNINDEXED) — FTS5 doesn't tokenize this column, just keeps
    -- it associated with the row. Schema of the JSON payload is the contract
    -- between build_registry.py and registry/store.py:
    --   {
    --     "cnpj": "33000167000101",
    --     "nome": "PETROBRAS",
    --     "kind": "cvm_company",         -- 'cvm_company'|'cvm_fund'|'susep'
    --     "sources": ["cvm","b3"],
    --     "tickers": ["PETR3","PETR4"],
    --     "cod_cvm": "9512",
    --     "codigo_fip": null,
    --     "extra": { ... source-specific fields ... }
    --   }
    payload UNINDEXED,

    tokenize='unicode61 remove_diacritics 2'
);

-- Build metadata (single-row-per-key key/value table). Lets the loader assert
-- schema compatibility and lets the CI cron decide whether content changed.
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Convention: build_registry.py inserts at minimum:
--   schema_version : "1"
--   built_at       : ISO-8601 timestamp
--   sources_json   : JSON object with per-source row counts
--   content_sha256 : hash of all payload rows (for CI no-op detection)
