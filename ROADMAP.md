# Roadmap & Next Steps

Status: **v0.3.1 — alpha.** CI live at [`.github/workflows/ci.yml`](.github/workflows/ci.yml). Public MCP: [`docs/DEPLOY_WORKERS_MCP.md`](docs/DEPLOY_WORKERS_MCP.md). Internal FastAPI/gVisor: [`docs/DEPLOY_GVISOR.md`](docs/DEPLOY_GVISOR.md).

## 🟢 Ready to use right now

- `pip install -e '.[dev]'` → venv with everything.
- `findata serve --host 0.0.0.0 --port 8000` → REST + MCP server.
- `findata bcb get selic -n 10` → CLI access to BCB.
- All unit tests pass (`pytest`), `ruff` and `mypy --strict` clean.

## 🟡 Immediate next steps (pick them up when you hit the WSL server)

1. **Run the server on WSL**
   ```bash
   # in WSL
   git clone https://github.com/robertoecf/openfindata.git
   cd openfindata
   python3 -m venv .venv && . .venv/bin/activate
   pip install -e .
   findata serve --host 0.0.0.0 --port 8000
   ```
   Or Docker: `docker compose up -d`.

2. **GitHub Actions CI**
   CI is live at [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

3. **Publish to PyPI**
   - Reserve the name: <https://pypi.org/project/openfindata/>
   - Create a release: `git tag v0.3.1 && git push --tags`
   - Add a `release.yml` workflow that runs on tags and publishes via
     [trusted publishing](https://docs.pypi.org/trusted-publishers/).

4. **Systemd / process manager on WSL**
   Minimal `findata.service` unit:
   ```ini
   [Unit]
   Description=Dados Financeiros Abertos
   After=network.target

   [Service]
   Type=simple
   User=yourself
   WorkingDirectory=/srv/openfindata
   ExecStart=/srv/openfindata/.venv/bin/findata serve --host 0.0.0.0 --port 8000 --no-banner
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

5. **Expose behind nginx or Caddy** if you want HTTPS. Caddy one-liner:
   ```
   findata.yourdomain.com { reverse_proxy localhost:8000 }
   ```

## 🔵 Feature roadmap (0.2+)

- **Rate limiting** (`slowapi`) when exposing publicly.
- **Observability** — structured JSON logs, `/metrics` (Prometheus exporter),
  optional OpenTelemetry via env vars.
- **Redis cache** — drop-in replacement for the in-memory LRU for multi-replica
  deploys.
- **ANBIMA indexes** — IMA, IMA-B, IDkA, IHFA.
- **B3 native** — scrape official CSVs/COTAHIST to remove the `yfinance` dep.
- **IBGE expansion** — PNAD Contínua, produção industrial, comércio varejista.
- **TypeScript SDK** — generate from the OpenAPI spec.
- **Webhooks / streaming** — SSE for "give me the new PTAX the moment BCB
  publishes it".

## 📚 Lessons from adjacent projects

Open-source peers and closed products we study as refs. Not a catalog, not
endorsements, not source adapters unless the note says so.

### From [OpenBB-finance/OpenBB](https://github.com/OpenBB-finance/OpenBB) (Python, global) — the reference 🐐

The closest large-scale analogue to what we're building, and the bar to measure
against. OpenBB's Open Data Platform is a *"connect once, consume everywhere"*
layer that exposes the same standardized data across a Python SDK, a CLI, a
FastAPI REST server, an MCP server for AI agents, Excel, and the OpenBB
Workspace UI. That is precisely our thesis (lib + REST + CLI + MCP over a single
normalized core), validated at scale.

Consulta 2026-09-04. On 2026-08-25 Didier Lopes announced the company
did not find product-market fit and is winding down. With OSS Capital they
committed to release Workspace, ODP, Copilot and the Excel add-in under a
*permissive* license
([OpenBB belongs to everyone](https://openbb.co/blog/openbb-belongs-to-everyone/)).
Order and timing TBD; hosted customers were told they would hear separately.
As of this check the drop has not landed: `OpenBB-finance/OpenBB` is still
AGPLv3; there is no public Workspace repo; [pricing](https://openbb.co/pricing/)
still lists Community / Lite ($2,400/yr) / Pro / Snowflake; ToS
(2026-07-08) still defines Paid Service Tiers. The blog post is a
commitment, not a license grant.

Evaluation:

- ✅ **Single normalized core, many surfaces.** Our `sources/<source>/` feeding
  one model that the Python lib, REST, CLI and `/mcp` all reuse mirrors their
  architecture — we are directionally correct, keep it that way.
- ✅ **MCP as a first-class surface.** OpenBB ships an MCP server alongside REST;
  validates our early bet on `/mcp` instead of treating it as an afterthought.
- 🟡 **Provider/extension system as installable packages.** OpenBB lets third
  parties add data sources *without forking core* — separate extension repos,
  discovered at runtime. Our `sources/` are in-tree today; a plugin/entry-point
  mechanism is the natural path once external contributors want their own
  source without a PR to core.
- 🟡 **"Build once, deploy everywhere" templates.** A scaffolding command for a
  new source (`findata new-source <name>`) would lower the contribution bar the
  way their extension template does.
- 🟡 **Spreadsheet surface.** Their Excel add-in is a reminder that many BR
  analysts live in spreadsheets; a thin `=FINDATA(...)` bridge over the REST API
  is a cheap, high-leverage future surface.
- 🟡 **Watch the promised source drop.** Workspace, Copilot and the Excel
  add-in are the product surfaces. Revisit when a repo and LICENSE exist.
  Do not treat the 2026-08-25 post as permission to copy those products.
- ❌ **Do not copy the commercial layer they are walking away from.**
  Account/Hub/Lite/Pro, dual AGPL+commercial licensing, and
  paid-provider marketplace machinery. Stay MIT and self-host-first.
- ❌ **Global/paid-provider breadth (FMP, Polygon, etc.).** Our scope is BR
  public sources with no API keys; chasing global paid providers would dilute
  the "if the data is public, the infra should be too" thesis.

### From [Tpessia/dados-findanceiros](https://github.com/Tpessia/dados-financeiros) (TS/NestJS, BR)

Already absorbed:

- ✅ **IPEA Data (OData v4)** — unique macro series with 1940s+ history, ported in v0.1.0.
- ❌ **Tesouro Direto D0 JSON** — endpoint has been retired (HTTP 410).
- ❌ **BCB SGS duplicates** — already covered, no action.

### From [gprossignoli/findata](https://github.com/gprossignoli/findata) (Python, global)

Student project, inactive, sync `requests`/RabbitMQ/MongoDB — most of the stack
is in the opposite direction of ours (async httpx + FastAPI + MCP). But two
ideas are worth copying:

- ✅ **Per-source top-level packages.** Our `src/findata/sources/<source>/`
  already follows this; codified in [CONTRIBUTING.md](CONTRIBUTING.md).
- ✅ **`*_adapter.py` naming for external deps.** Consider renaming internal
  clients (e.g., future `yfinance_adapter.py`, `anbima_adapter.py`) to make
  the boundary explicit and greppable. Low-priority refactor.
- 🟡 **Use-cases as classes.** Not critical today (our functions are already
  tiny), but if a flow grows to orchestrate multiple adapters it should
  graduate into a `UseCase` class so CLI / HTTP / MCP can all reuse it.
- ❌ **Clean-Architecture three-folder ceremony** (`domain/application/
  infraestructure/`). Overkill for stateless wrappers — skip.
- ❌ **APScheduler / RabbitMQ / MongoDB.** A library shouldn't embed a
  scheduler or a broker; let callers (cron, Airflow, GH Actions) drive it.
- ❌ **yfinance fork.** They fork to fix non-US tickers; we already use
  mainline yfinance for B3 without modification.

### From [ETF1](https://etf1.com.br) (closed, BR) — ETF terminal + OnePro

Consulta 2026-09-04. Stop Loss Club / IBEE. Free Next.js ficha for B3, US and
Irish ETFs (plus stocks, BDRs, FIIs, funds, Tesouro). Paid OnePro is
allocation / Monte Carlo / GBI, not a data API. Notes:
[`docs/ETF1_SURVEY.md`](docs/ETF1_SURVEY.md),
[`docs/ETF1_PRODUCT_REF.md`](docs/ETF1_PRODUCT_REF.md).

Evaluation:

- ✅ **ETF ficha as a field set, not a scrape.** Identity, legal, TER, index,
  holdings, style box. Implement from CVM cadastro + CDA + B3 + registry.
- ✅ **Index complement + fee, stamped reconstructed.** Short ETF series
  spliced onto the official index. Useful helper; never silent.
- ✅ **`llms.txt` as the agent door.** What the product is, which URLs to
  open, what it does not do (no real-time quotes, no recommendation).
- 🟡 **Analysis contract.** Percentiles, Ulcer, max DD, monthly heatmap —
  Chart Lab only after a normalized return series exists.
- ❌ **No `src/findata/sources/etf1/`.** No anonymous REST. OnePro MCP is
  paid (`onepro:read`). Terms §09 forbid systematic extract and unauthorized
  crawlers. Not a resolver cascade step.
- ❌ **OnePro modules.** Allocation, Monte Carlo and GBI are a planning
  product. Out of scope here.

## 🧪 Known caveats

- **CVM financial statements (DFP/ITR)** download a multi-hundred-MB ZIP for a
  full year — always pass `cnpj=` when hitting `/cvm/financials/*`.
- **Fund daily NAV** files are ~50 MB/month — same recommendation: filter by
  `cnpj=`.
- **yfinance** is a core dependency since v0.1.0; if you use
  `pip install openfindata --no-deps` and skip it, `/b3/*` returns `503`.
- **fastapi-mcp** is pinned at a minimum version; if your deployment picks up
  a major-version break, `/mcp` is silently disabled but the REST API keeps
  serving.
