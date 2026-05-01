# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.1] — 2026-04-29

Patch release fixing 5 bugs caught in adversarial review of v0.3.0 by
external LLM (`gpt-5.4 xhigh` via tmux). Four are real correctness /
availability issues in the registry query path; the fifth is metadata
hygiene in the BCB SGS catalog.

### Fixed

- **DoS via FTS5 reserved words** in `/registry/lookup`. `q=OR` (also
  `AND`, `NOT`, `NEAR`) raised `sqlite3.OperationalError: fts5: syntax
  error near "OR"` and surfaced as **500 Internal Server Error** to any
  caller. `_normalize_query` now phrase-quotes reserved tokens so they
  go to FTS5 as literals, never operators.
- **FTS5 syntax injection** in `/registry/lookup`. User-supplied
  operators (`q=PETR4 NOT VALE3`) used to alter query semantics and
  return attacker-controlled results. Now neutralized via the same
  phrase-quoting pass.
- **Prefix / fragment search did not work** despite the contract in
  `routers/registry.py` and the docstring in `registry/__init__.py`
  promising "company-name fragment" / "prefix searches". `q=PETROBR`
  returned 0 hits. Fix: every non-reserved token now gets a `*` suffix
  for FTS5 prefix matching. `q=PETROBR` correctly resolves to PETROBRAS.
- **Labeled identifiers stopped resolving**. `q="CNPJ: 33.000.167/0001-01"`,
  `q="FIP 05886"`, `q="CVM 9512"` all returned 0 because the alpha label
  contaminated the joined-form variant (`CNPJ33000167000101` doesn't
  exist as a token). Fix: third query variant — digits-only-joined —
  rescues these inputs.
- **`cdb` SGS series flagged as historical-only**. `code=3946` ("Taxa
  média de CDB pré-fixado") was discontinued by BCB in 2012-12; the
  catalog now documents this in the entry name and a comment so users
  who pick `findata bcb get cdb` aren't surprised by ancient data.

### Added

- 9 regression tests covering each of the 4 fixed query-path bugs:
  reserved-word safety (4 tokens × asserts), prefix matching, labeled
  CNPJ resolution, FTS injection neutralization. 168 → **176 tests**.

### Internal

- `_FTS5_RESERVED` constant lists FTS5 operators we have to escape.
- New helper `_escape_token(t)` centralizes quote-or-prefix logic;
  `_normalize_query` now produces up to 3 OR'd variants (spaced /
  joined / digits-only-joined) for maximum input forgiveness.

## [0.3.0] — 2026-04-28

Cross-source CNPJ resolver — embedded SQLite registry shipped inside the
wheel. Single FTS5 `MATCH` query handles CNPJ (with or without mask),
B3 ticker, CVM code, SUSEP FIP code, and fuzzy name lookups uniformly,
with BM25 rank discriminating exact-match from fuzzy.

Sprint 5.5 (parallel) added BCB SGS catalog expansion (17 → 71 named
series) and ANBIMA IMA historical fetcher.

### Added

- **`findata.registry`** — read-only async store over the embedded
  `registry.sqlite` (~50k entities: CVM companies, CVM funds, SUSEP).
  Functions: `lookup(query, limit)` and `get_meta()`. Pydantic models
  `Entity` (with BM25 `rank`) and `LookupResult`.
- **REST endpoints**: `GET /registry/lookup?q=...&limit=...` and
  `GET /registry/meta`. Auto-exposed as MCP tools via `fastapi-mcp`.
- **CLI**: `findata registry lookup <query>` and `findata registry meta`.
  Rich table output with rank interpretation footnote.
- **`scripts/build_registry.py`** — offline regenerator that pulls from
  CVM (companies + funds), SUSEP, and B3 (index portfolios for ticker
  enrichment). Writes the canonical SQLite + meta KV table including
  `content_sha256` for CI no-op detection.
- **`.github/workflows/rebuild-registry.yml`** — weekly cron (Mon 06:00
  UTC) that rebuilds the registry and opens a PR if content hash differs.
  Manual `workflow_dispatch` trigger for ad-hoc regeneration.
- **BCB SGS catalog**: 17 → 71 named series — inflation breakdown
  (livres / monitorados / serviços / bens / núcleos), monetary aggregates
  (M1–M4), credit (saldo SFN, inadimplência, spread), external sector
  (balança, conta corrente, IDP, reservas), public sector (DBGG, primário,
  juros nominais), confidence (ICC FGV, ICEI CNI), and more.
- **ANBIMA IMA history**: `get_ima_history(family, start, end)` fetches
  historical IMA data points via ANBIMA's "Série Histórica" form
  (`ima-sh-down.asp` POST), validated against 14 years of data. Bounded
  concurrency, holiday-aware (handles "Não há dados disponíveis" banner),
  per-date 24h cache.
- **`aiosqlite >= 0.20`** added to core deps (pure Python, ~50KB).

### Fixed

- `scripts/build_registry.py` token normalization split: codes (CNPJ,
  ticker, cod_cvm) collapse punctuation, names preserve word boundaries.
  Without this fix, masked CNPJ `"33.000.167/0001-01"` fragmented into
  five tokens and exact CNPJ search returned 0 hits.
- `_normalize_query` produces `(spaced) OR (joined)` for inputs with
  punctuation — masked CNPJ resolves the same as bare digits.

### Known limitations (v1)

- B3 ticker enrichment misses entities where B3's `nome_ativo` differs
  from CVM's `nome_comercial` (e.g. `ITAUUNIBANCO` vs `ITAU UNIBANCO`).
  v2 candidate: fuzzy match or B3 endpoint exposing `cod_cvm` directly.
- CVM funds dataset (`cad_fi.csv`) is dominated by `CANCELADA` entries
  (46,566 of 46,810). Likely a legacy endpoint; consumers can filter via
  `extra.situacao` in the payload.
- Same legal entity may appear under multiple `cod_cvm` records, causing
  duplicate hits on CNPJ lookups. v2: dedupe on CNPJ at build time.

### Stats

- Tests: 117 → **168** (+51)
- REST endpoints: 73 → **75** (+2)
- Wheel size: 4.2 MB compressed (28 MB uncompressed; sqlite compresses
  heavily inside the zip)
- Registry build time: ~5 seconds against live BCB/CVM/SUSEP/B3

## [0.2.0] — 2026-04-28

Massive expansion of the public-data catalog across four sprints, each
adversarially reviewed by an external LLM (`gpt-5.4 xhigh` via tmux):
14 real bugs caught and fixed before release. Test count grew from 57
to 117; REST routes from 35 to 73; fonts modeled from 6 to 10.

### Sprint 1 — Event streams + B3 official history

- CVM IPE — fatos relevantes / comunicados (event stream)
- CVM FCA — formulário cadastral (B3-ticker → CNPJ resolver)
- B3 COTAHIST — official daily-quotes time series since 1986
- B3 indices — composição teórica (IBOV, IBrX, SMLL, IDIV, IFIX + 14 sectoriais)

### Sprint 2 — Especialised investment funds

- CVM FII — Fundos Imobiliários (geral + complemento)
- CVM FIDC — Fundos de Direitos Creditórios (TAB I/IV/VII)
- CVM FIP — Fundos de Investimento em Participações

### Sprint 3 — Public-finance accounting + federal-tax revenue

- Tesouro SICONFI — RREO/RGF/entes (5,598 entidades reportando)
- Receita Federal — arrecadação por UF (45 tributos × meses since 2000)

### Sprint 4 — Energy auctions + insurance entities

- ANEEL leilões — geração + transmissão (auction prices since 1999)
- SUSEP empresas — 233 supervised insurance/previdência entities
- ICP-Brasil chain trust via `truststore` integration in shared http client

### Added — Sprint 4: ANEEL energy auctions + SUSEP supervised entities

Two new sources rounding out the public-data catalog with energy and
insurance:

- **`get_aneel_leiloes_geracao(year=, fonte=, uf=)`** — every winning
  generation-auction bid since 2005 (A-3 / A-5 / A-6 / LFA / LEN, plus
  energia nova, energia existente, etc.). 26 columns including
  potência instalada (MW), garantia física, preço-teto / preço-leilão
  (R$/MWh), deságio, investimento previsto, duração do contrato, UF e
  empresa vencedora. Source: ANEEL CKAN (resource UUID stable).
- **`get_aneel_leiloes_transmissao(year=, uf=)`** — every winning
  transmission-line lot since 1999, with extensão (km), MVA das
  subestações, RAP de edital × RAP do vencedor, deságio (%), prazo de
  construção (meses), UF, empresa vencedora.
- **`get_susep_empresas / search_susep_empresa`** — canonical SUSEP
  roster of every supervised entity (insurance, previdência, capitalização,
  resseguro). Three columns: CodigoFIP, NomeEntidade, CNPJ. Useful as
  a code → CNPJ resolver and to filter joint-product feeds. Source:
  ``www2.susep.gov.br/menuestatistica/ses/download/LISTAEMPRESAS.csv``.

### Changed — http_client.py uses OS trust store

- `findata.http_client` now configures httpx with a ``truststore``-
  backed SSL context when available (added as a core dep, ``>=0.10``),
  falling back to ``ssl.create_default_context()`` otherwise. This
  fixes ``CERTIFICATE_VERIFY_FAILED`` on Brazilian government sites
  signed under the ICP-Brasil chain (SUSEP being the trigger), which
  isn't in certifi's bundle but is in macOS Keychain / WSL CA store.

### Added — REST routes (Sprint 4)

- ``/aneel/leiloes/{geracao,transmissao}``
- ``/susep/empresas``, ``/susep/empresas/search``

### Added — CLI (Sprint 4)

- ``findata aneel leiloes [--tipo geracao|transmissao] [-y YYYY] [-f FONTE] [--uf UF]``
- ``findata susep search <query>``

### Tests

- ``tests/test_aneel_leiloes.py`` — 6 respx-mocked tests covering
  Brazilian-decimal parsing, year / fonte / uf filters, RAP +
  extensão parsing, transmissão filter combinations.
- ``tests/test_susep_empresas.py`` — 3 respx-mocked tests covering
  malformed-row skip, case-insensitive name search, and short-query
  refusal.
- 114 unit tests pass total (was 105). ruff + ruff-format + mypy
  --strict clean.

### Live smoke (Sprint 4)

- ANEEL eólicas: 801 winning empreendimentos (Baraúnas XV: 49 MW,
  R$ 175/MWh; AW São João: 25 MW, R$ 178/MWh).
- ANEEL transmissão 2024: 18 lotes (Teresina IV - Graça Aranha:
  RAP/ano R$ 112.5M).
- SUSEP empresas: 233 entidades; ``search('porto seguro')`` → 3
  matches (Seguros Gerais, Vida e Previdência, Capitalização).

### Defensive

- ``empresas.py`` strips a leading blank line that the live SUSEP CSV
  ships with — without it, ``csv.DictReader`` interprets the empty
  first row as the header and returns 0 records.

### Added — Sprint 3: public-finance accounting + federal-tax revenue

Two new sources connecting Dados Financeiros Abertos to Brazil's public-sector
accounting + federal-tax flows:

- **`get_rreo / get_rgf / get_entes`** — Tesouro SICONFI API, the
  Tesouro Nacional's datalake for the bimonthly RREO (Relatório
  Resumido de Execução Orçamentária) and quadrimestral RGF (Relatório
  de Gestão Fiscal) reports filed by every federal, state, and
  municipal entity in Brazil under the LRF. REST + JSON, public,
  cached pagination handled transparently (5000-row pages, walks until
  ``hasMore=false``). 5,598 entities live (União + 26 UFs + DF + 5,570
  municipalities). Filters: ``cod_ibge``, ``co_anexo``, ``co_poder``
  for RGF.
- **`get_arrecadacao(year=, month=, uf=, tributo=)`** — Receita
  Federal monthly tax revenue by UF. Single CSV at
  ``gov.br/receitafederal/dados/arrecadacao-estado.csv`` with ~45 tax
  categories (IRPF, IRPJ, IRRF, COFINS, PIS, CSLL, IPI sub-categories,
  IOF, CIDE, CPSSS, etc.) since 2000. Surfaced as long-form (one row
  per period × UF × tributo) so callers can pivot without committing
  to today's column shape (Receita has renamed columns over time).

### Added — REST routes (Sprint 3)

- ``/tesouro/siconfi/{rreo,rgf,entes}``
- ``/receita/arrecadacao``, ``/receita/tributos``

### Added — CLI (Sprint 3)

- ``findata tesouro rreo <COD_IBGE> -y YYYY -b BIMESTRE [-a ANEXO]``
- ``findata tesouro entes [--uf SP]``
- ``findata receita arrecadacao -y YYYY [-m MM] [--uf SP] [-t IRPF]``

### Tests

- ``tests/test_tesouro_siconfi.py`` — 6 respx-mocked tests covering
  RREO/RGF parsing, **pagination follow-up** when ``hasMore=true``,
  ``co_anexo`` / ``co_poder`` query-param passthrough, empty payload,
  defensive ``cod_ibge``-missing skip on entes.
- ``tests/test_receita_arrecadacao.py`` — 6 respx-mocked tests
  covering long-form expansion, UF + tributo + year/month filters,
  empty-cell tolerance, malformed-month skip, and the **trailing
  empty-column header drop** (Receita's CSV ends every line with ``;``,
  yielding an empty-name "column" that csv.DictReader picks up — we
  filter it out so it doesn't pollute ``list_tributos``).
- 101 unit tests pass (was 89, +12). ruff + ruff-format + mypy --strict
  clean.

### Live smoke (Sprint 3)

- União 2024-B6 RREO Anexo 06: 6,962 registros (receitas R$ 3.6T
  previsão inicial / R$ 692B no bimestre).
- SICONFI entes: 5,598 total (União + 26 UFs + DF + 5,570 munis).
- Receita SP 2024-01 IRPF: R$ 1,160,717,531.

### Deferred to Sprint 4

- **SUSEP** open data — site uses ``.aspx`` pages with dropdown-driven
  downloads; needs more reverse-engineering than this sprint's budget.
- **ANEEL** — ``dadosabertos.aneel.gov.br`` returned TLS connection-reset
  during scoping; will retry under the next sprint.

### Added — Sprint 2: especialised investment funds (FII / FIDC / FIP)

Three CVM products that the regular FI catalog (`funds.py`) doesn't
cover, each with its own publication path, cadence, and shape:

- **`get_fii_geral / complemento(year, cnpj=None, month=None)`** —
  Fundos de Investimento Imobiliário. Annual ZIP with three CSVs
  (`geral`, `complemento`, `ativo_passivo`); we ship the first two:
  cadastral facet (segmento, mandato, gestão, administrador) and
  complement facet (PL, valor patrimonial cota, cotistas breakdown by
  type — PF / PJ não-financ / banco / EAPC / EFPC / RPPS / etc.).
- **`get_fidc_geral / pl / direitos_creditorios(year, month, cnpj=None)`** —
  Fundos de Investimento em Direitos Creditórios. Monthly ZIP fans into
  twelve schedule-CSVs (TAB_I through TAB_X); we expose the three
  highest-density: TAB_I (cadastral), TAB_IV (PL final + médio), TAB_VII
  (direitos creditórios com / sem risco + vencidos a adquirir).
- **`get_fip(year, cnpj=None, quarter=None, include_raw=False)`** —
  Fundos de Investimento em Participações. Annual single CSV (no zip
  wrapper) with one row per fund per quarter and 54 columns covering
  capital subscription / integralization, cotistas breakdown, classe de
  cotas, direitos políticos / econômicos. `include_raw=True` carries
  the full row for callers that need the long tail.

### Added — REST routes (Sprint 2)

- `/cvm/funds/fii/{geral,complemento}`
- `/cvm/funds/fidc/{geral,pl,direitos-creditorios}`
- `/cvm/funds/fip`

### Added — CLI (Sprint 2)

- `findata cvm fii <CNPJ> -y YYYY [-m MM]` — segmento/mandato/PL/cotistas
- `findata cvm fidc <CNPJ> -y YYYY -m MM` — classe/PL/direitos creditórios
- `findata cvm fip <CNPJ> -y YYYY [-q Q]` — capital, cotistas, classe

### Tests

- `tests/test_cvm_fii_fidc_fip.py` — 9 respx-mocked tests covering FII
  filter matrix, FIDC TAB_I/IV/VII parsing (Brazilian decimals, ISO-8859-1
  encoding), FIP filter + quarter + raw-row preservation.
- 87 unit tests pass total (was 78). ruff + ruff-format + mypy --strict clean.

### Live smoke (Sprint 2)

- FII PÁTRIA LOG (`11.728.688/0001-47`) 2026-02: PL R$ 7.0B, 544k cotistas,
  segmento Multicategoria, gestão Ativa.
- FIDC fevereiro 2026: 3,736 fundos cadastrados.
- FIP Q4 2023: 2,068 informes trimestrais.

### Defensive

- FIP `_safe_raw()` filters `None` keys from `csv.DictReader` output —
  pydantic would otherwise reject malformed rows where the data has more
  delimiters than the header (real CVM data sometimes has trailing empty
  fields).

### Added — Sprint 1: event streams + B3 official history

Four new high-density public sources, wiring listed-company filings,
ticker resolution, and authoritative price history into the catalog:

- **`get_ipe(year, cnpj=None, categoria=None)`** — CVM IPE event stream
  (fatos relevantes, comunicados, atas, calendários, boletins de voto).
  One row per filing with the original PDF link on CVM's RAD system.
- **`get_fca_geral / valores_mobiliarios / dri`** — CVM FCA cadastral
  form. `valores_mobiliarios` is a B3-ticker → CNPJ resolver (e.g.
  `ticker="PETR4"` → `33.000.167/0001-01`, segmento, dt_inicio_listagem).
  `geral` carries setor / situação / exercício / website. `dri` is the
  IR contact card.
- **`get_cotahist_year/month/day(year, [m], [d], ticker=None)`** — B3
  COTAHIST official daily-quotes time series (1986+). Fixed-width 245
  cols, prices stored in cents, parsed line-by-line so the 85 MB
  annual file streams without RAM bloat. Filters: `ticker`, `market_codes`
  (CODBDI whitelist — `02` lote padrão, `78`/`82` options, etc.).
- **`get_index_portfolio(symbol)`** — B3 index composition (IBOV,
  IBrX-50/100, SMLL, IDIV, IFIX, plus 14 sectoral) via the `indexProxy`
  JSON endpoint. Returns every constituent with weight (%), share class,
  and theoretical quantity. Refreshed quarterly.

### Added — CLI (Sprint 1)

- `findata cvm ipe <CNPJ> -y YYYY [--categoria "Fato Relevante"]`
- `findata cvm ticker <TICKER> -y YYYY` — resolve ticker → company facts
- `findata b3 cotahist <TICKER> -y YYYY [-m MM] [-d DD]`
- `findata b3 index <SYMBOL>` — print full theoretical portfolio

### Added — REST routes (Sprint 1)

- `/cvm/companies/ipe`, `/cvm/companies/fca/{geral,securities,dri}`
- `/b3/cotahist/{year,month,day}/...`, `/b3/indices`, `/b3/indices/{symbol}`

### Fixed — Codex adversarial review (Sprint 1)

Four real bugs caught by a `gpt-5.4 xhigh` peer review against live
upstream files:

- **COTAHIST FATCOT not applied** — closed-end funds (FNAM11, FNOR11,
  …) quote prices for a *lot* of FATCOT shares (typically 1000),
  affecting 584/2.6M records in COTAHIST_A2024. The parser now divides
  by `FATCOT` so all `preco_*` fields are canonical per-share values.
  `volume_financeiro` is unchanged (it's already total cash).
- **B3 indices pagination** — `get_index_portfolio` only fetched page
  1, silently dropping 22 of ITAG's 222 components. Now loops pages
  until `totalPages` is reached (capped at 10 pages = 2000 issues).
- **NBSP / trailing-whitespace stripping** — IPE's free-text fields
  (`assunto`, `tipo_apresentacao`, …) carry trailing `\xa0` in real
  CVM data. Optional fields now go through a `_opt()` helper that
  strips and drops empty (Python's `.strip()` already treats NBSP as
  whitespace). Same fix applied to FCA for consistency.
- **`get_cotahist_year()` RAM bomb** — unfiltered annual call would
  materialise 2.6M Pydantic models. Now requires `ticker` or
  `market_codes` and raises `ValueError` otherwise. Per-month and
  per-day calls are unaffected.

### Tests

- `tests/test_cvm_ipe_fca.py` — 9 respx-mocked tests (IPE filter
  matrix + NBSP regression + FCA geral/securities/DRI).
- `tests/test_b3_cotahist_indices.py` — 12 respx-mocked tests covering
  fixed-width parser (cents → reais), **FATCOT-1000 regression**,
  **unfiltered-annual guard**, **pagination regression**, ticker filter,
  market-code whitelist, base64 round-trip, Brazilian-decimal weight
  parsing.
- 78 unit tests pass (was 57). ruff + ruff-format + mypy --strict clean.

### Live smoke

- Vale (`33.592.510/0001-54`) IPE 2026: 4 fatos relevantes parsed.
- PETR4 FCA 2025 → CNPJ `33.000.167/0001-01`, Nível 2 segmento.
- IBOV: 83 ativos, top weight VALE3 11.477%, redutor 14.469.518,98.
- PETR4 COTAHIST 2024-03 (lote padrão): 20 sessões, prices in R$.

### Added — CVM fund deep dive

Three new CVM fund products on top of the existing catalog + daily NAV:

- **`get_fund_holdings(cnpj, year, month)`** — full portfolio (CDA file).
  Every position the fund holds, classified by CVM block (BLC_1 títulos
  públicos, BLC_2 cotas de fundos, BLC_4 ações/debêntures, BLC_8
  disponibilidades, etc., plus CONFID / PL / FIE). The monthly zip is
  ~150 MB unzipped, so a CNPJ filter is required and we line-stream
  every block in-place. Optional `blocks=` whitelist.
- **`get_fund_lamina(year, month, cnpj=None)`** plus
  `get_fund_monthly_returns()` and `get_fund_yearly_returns()` — the
  regulatory factsheet (lâmina) with strategy, restrições, alavancagem
  caps, plus per-month and per-year returns vs benchmark.
- **`get_fund_profile(year, month, cnpj=None)`** — perfil mensal:
  cotistas count broken down by type (PF private/varejo, PJ
  financeira/não-financeira, banco, corretora).

### Added — period discovery via HTML scrape

- **`findata.sources.cvm.list_files / list_periods / latest_period`** —
  scrapes `https://dados.cvm.gov.br/dados/<cat>/<product>/DADOS/`
  directly so we don't hard-code year ranges that go stale. New
  `/cvm/funds/periods?product=...` route exposes it.
- Pattern lifted from `gabrielguarisa/brdata`'s `_get_table_links`,
  reimplemented async-native against our shared httpx client.

### Added — CLI

- `findata cvm holdings <CNPJ> -y YYYY -m MM [--blocks BLC_1,BLC_4]`
- `findata cvm lamina <CNPJ> -y YYYY -m MM`
- `findata cvm profile <CNPJ> -y YYYY -m MM`

### Tests

- `tests/test_cvm_funds.py` — 9 respx-mocked tests covering directory
  listing, block-label decoding, CDA filter + whitelist, lâmina main +
  monthly + yearly returns, perfil filter + no-filter passthrough.
- 57 unit tests pass total (was 48). ruff + mypy --strict clean.

### Live smoke

Validated end-to-end against real CVM with `00.280.302/0001-60`
(Bradesco H FIF — Crédito Privado): 6 holdings (R$ 270M concentrados em
cotas de outros fundos), lâmina com objetivo CDI + 0% alavancagem, 1491
cotistas PF varejo + 50 PJ varejo + 24 PF private.

### Added — ANBIMA as a public-data source

- **`findata.sources.anbima`** — covers IMA family snapshot (IRF-M, IMA-B,
  IMA-S, IMA-Geral, with sub-indices like `IRF-M 1+`, `IMA-B 5`, etc.), the
  ETTJ zero-coupon yield curve (Pré, IPCA, inflação implícita per vértice),
  and daily debentures secondary-market quotes.
- Implementation reads ANBIMA's free static files at
  `www.anbima.com.br/informacoes/*` (XLS / CSV / TXT). No credentials, no
  API keys, no cadastro institucional — same canonical numbers as ANBIMA's
  commercial Sensedia API, just delivered as files.
- **Rotas:** `/anbima/{ima,ettj,debentures}`, all public.
- **CLI:** `findata anbima {ima,ettj,debentures}` (with `--family`,
  `--date`, `--emissor` filters).
- **`xlrd>=2.0.1`** added as a core dependency to parse the legacy `.xls`
  files ANBIMA still publishes.

### Added — auth framework (groundwork for future credentialed sources)

- **`findata.auth`** module — generic `OAuth2ClientCredentials` flow with
  in-process token cache and customisable header conventions for non-spec
  gateways (Sensedia, etc.). Surfaces `AuthError` and
  `MissingCredentialsError` for callers.
- The framework is intentionally unused by the current ANBIMA integration
  (which is fully public). It stays in the codebase for future sources
  that genuinely require auth — SUSEP, BNDES, CETIP, etc. The recipe for
  contributors is documented in `docs/SOURCES_WITH_AUTH.md`.

### Background

We initially shipped ANBIMA as an authenticated integration, validated the
OAuth2 flow live, but discovered ANBIMA's developer programme isn't
self-serve — it requires institutional membership or a commercial contract.
We pivoted to the equivalent public file feeds, which give the same data
without gating. The auth scaffolding stays so the next genuinely
credentialed source ships in hours rather than days.

### Added — public MCP server ergonomics

- **Rate limiting** via `slowapi` — `FINDATA_RATE_LIMIT_DEFAULT` env var
  (default `60/minute;1000/day`), keyed by `X-Forwarded-For` then
  remote address. Emits `X-RateLimit-Limit/Remaining/Reset` headers.
  Toggle with `FINDATA_RATE_LIMIT_ENABLED=false` for local dev.
- **`GET /stats`** endpoint — uptime, cache size, sources, MCP enabled,
  rate-limit state. Cheap to poll from status pages.
- **`deploy/findata-br.service`** — hardened systemd unit (NoNewPrivileges,
  ProtectSystem=strict, MemoryMax=512M).
- **`deploy/docker-compose.prod.yml`** — localhost-only binding + optional
  `cloudflared` sidecar behind a `--profile tunnel` flag.
- **`docs/DEPLOY_PUBLIC.md`** — full walkthrough (pt-BR) to stand the
  server up on Windows+WSL2 behind Cloudflare Tunnel for free.
- **Community scaffolding** — issue templates (`new-source`, `bug`) with
  a `config.yml` that links to Discussions + the deploy guide, plus
  `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1).

### Changed — legacy cleanup

- **Extract `findata._cache.TTLCache`**, eliminating three copy-pasted
  module-level caches (`_companies/_companies_at/_CACHE_TTL` in CVM
  companies, `_catalog/_catalog_at/_CATALOG_TTL` in CVM funds,
  `_parsed/_parsed_at/_PARSED_TTL` in Tesouro bonds) and the `global`
  keyword dance that went with them.
- **Extract `findata._odata.parse_odata`** — the single generic OData
  `value[]` → Pydantic parser that lived in `bcb/focus.py`. BCB PTAX's
  `get_ptax_*` and `get_currencies` now use it too, dropping an ad-hoc
  `_parse_quotes` and a hand-rolled dict-unpacking list comprehension.
- **Lazy B3 thread-pool** — `ThreadPoolExecutor` is created on first
  use and drained by `close_executor()`, wired into the FastAPI
  lifespan. Importing the module no longer costs a live pool.
- **Type-safe CLI `_run`** — now `_run(coro: Coroutine[Any, Any, T]) -> T`
  via a `TypeVar`, so `typer` handlers don't leak `Any` to callers.
- **Pin `fastapi-mcp>=0.4`** and drop the defensive `mount()` fallback
  — the current API is `mount_http()` and the fallback was dead code.
- Docstrings added to previously empty `__init__.py` files (`api/`,
  `api/routers/`, `sources/`).
- Silence upstream `PydanticDeprecatedSince211` warning at the pytest
  level — it's triggered from inside pydantic-core when we validate a
  `ConfigDict` and not something our code can fix.

### Added

- **IPEA Data** source (OData v4) — access to ~8k curated macroeconomic
  series with endpoints for catalog listing, by-SERCODIGO values,
  metadata, and full-text search. CLI: `findata ipea {catalog,get,search}`.
- IPEA router at `/ipea/*` and curated built-in catalog.
- **Git guardrails** inspired by wealthuman's biome+eslint split:
  - Ruff now enforces AI guardrails (complexity `C901`, max-args `PLR0913`,
    magic-value `PLR2004`, branches `PLR0912`, returns `PLR0911`, stmts
    `PLR0915`), flake8-bandit `S*`, `no-print` `T201`, `ERA` commented-out.
  - Per-context overrides for tests (ignore `S`/`PLR2004`) and FastAPI
    routers (ignore `B008`).
  - `.githooks/pre-commit` (ruff + format check on staged .py + optional
    `ggshield` secret scan) and `.githooks/pre-push` (full `ruff check` +
    `mypy --strict` + `pytest`). Installed via
    `bash scripts/git/install-hooks.sh` → `core.hooksPath = .githooks`.
- `CONTRIBUTING.md` documenting the guardrail philosophy and dev workflow.
- `ROADMAP.md` section comparing Dados Financeiros Abertos against Tpessia/dados-financeiros
  and gprossignoli/findata (lessons learned, what we adopt / skip).

### Changed

- README fully translated to **pt-BR** and the top banner now renders as an
  ASCII code block (`DADOS FINANCEIROS ABERTOS`), matching CLI-tool repo conventions
  instead of relying on a remote typing-svg image that some GitHub clients
  were failing to render.
- Badges trimmed to working ones (CI, version, Python, license, status)
  — removed PyPI/Python-version badges that returned 404 while the package
  is unpublished.

## [0.1.0] — 2026-04-22

### Added

- Initial public release of **Dados Financeiros Abertos**.
- REST API (FastAPI) with routers for BCB, CVM, B3, IBGE, Tesouro.
- Auto-generated MCP server mounted at `/mcp` (via `fastapi-mcp`).
- CLI (`findata`) with animated gradient banner and rich-text tables.
- Async Python library with shared httpx client (connection pool, retries,
  LRU cache, OData-safe URL builder).
- BCB sources: SGS (18 curated series), PTAX (USD/EUR/all currencies,
  period endpoint), Focus (annual, monthly, Selic-per-COPOM, Top-5).
- CVM sources: registered companies (search + listing), DFP/ITR financial
  statements, fund catalog and daily NAV.
- IBGE Agregados v3 source with IPCA breakdown by 10 major groups.
- Tesouro Transparente historical bond CSV with caching.
- B3 quotes via `yfinance` (optional extra `[b3]`).
- Unit tests for http client, models, parsers, and API (network-free, via
  `respx`). Integration suite gated by `pytest -m integration`.
- `Dockerfile` + `docker-compose.yml` for one-command deployment.
- GitHub Actions CI matrix (3.11/3.12/3.13).
