# AGENTS.md — Dados Financeiros Abertos

This file is for coding agents working in this repository. Keep it practical:
follow the project conventions, avoid speculative dependencies, and produce
reproducible data work.

## Project baseline

- Canonical working directory: the repository root, i.e. the directory that
  contains this `AGENTS.md`.
- Project name: Dados Financeiros Abertos.
- Distribution/package slug: `openfindata`.
- Import package and CLI remain `findata` for compatibility.
- Scope: Python library + REST API + MCP server + CLI for Brazilian public
  financial data.
- Prefer public, reproducible sources. Do not introduce API keys, tokens, or
  private credentials into code, tests, docs, examples, or generated artifacts.
- Keep repo-facing Markdown disciplined and functional. Avoid decorative emoji.
- Do not commit generated caches, local virtualenvs, temporary chart outputs, or
  binary artifacts other than the generated registry SQLite already owned by the
  project.

## Quality gates

Before a code change is considered ready, run the smallest relevant check first,
then the full gate from the repository root before merging or release work:

```bash
.venv/bin/ruff format --check src/ tests/ scripts/
.venv/bin/ruff check src/ tests/ scripts/
.venv/bin/python -m mypy src/findata
.venv/bin/python -m pytest tests/ -q
```

Ruff owns the Biome-like formatter/lint baseline and the ESLint-like AI
guardrails configured in `pyproject.toml`.

For documentation-only edits, at least run:

```bash
git diff --check
```

## Source integration pattern

- New source modules live under `src/findata/sources/<source>/`.
- Add route, CLI, tests, docs, and mocked HTTP coverage together when exposing a
  new public dataset.
- Use `findata.http_client.get_json` / `get_bytes` for network access.
- Unit tests should not hit live APIs. Use `respx`; mark live checks as
  `@pytest.mark.integration`.
- Keep `mypy --strict` clean for new code.

## Base dos Dados / BigQuery usage

Base dos Dados is a supported free logged-in source. Treat it differently from
commercial-entitlement APIs such as ANBIMA's authenticated developer products:
SQL, Python and R access are free/self-serve, but BigQuery still requires the
operator's Google login and a billing project.

- Do not embed Google credentials, service-account JSON, refresh tokens, or
  project-specific secrets in code, tests, docs, examples, or generated
  artifacts.
- Prefer the local env var for interactive work:

```bash
export FINDATA_BD_BILLING_PROJECT_ID="<google-cloud-project-id>"
```

- The project also accepts `BASE_DOS_DADOS_BILLING_PROJECT_ID` and
  `GOOGLE_CLOUD_PROJECT` as fallbacks.
- Use the Project ID, not the display name.
- BigQuery can bill by bytes processed. Base dos Dados access is free, and
  BigQuery has a free monthly quota, but queries may still consume billable
  quota. Start with tiny `LIMIT` queries before broad scans.
- Prefer the `findata` CLI wrapper for local checks:

```bash
.venv/bin/findata basedosdados sql br_bd_diretorios_brasil municipio --limit 5
.venv/bin/findata basedosdados query \
  'SELECT id_municipio, nome FROM `basedosdados.br_bd_diretorios_brasil.municipio` LIMIT 5'
```

- For user-facing or PR evidence, report the billing project used only when it
  is already known to the user or explicitly provided in the task. Do not expose
  private credential paths.

## Graphics and chart generation standards

Agents may use this repo to generate exploratory charts for users. Treat the
Chart Lab (`/charts`, `src/findata/web/templates/charts.html`,
`src/findata/web/static/chart-explorer.js`) as the canonical visual and
informational reference, but not as a mandatory renderer.

Short runbook for any one-off chart request:

1. Generate an audit data file next to the visual artifact, preferably tidy CSV.
2. Generate a clear visual artifact (SVG, PNG, HTML, or Lightweight Charts HTML)
   with the same minimum information block used by Chart Lab.
3. Save or print the script/route used, data path, visual output path, and
   renderer.
4. Keep temporary scripts, CSVs, PNGs, SVGs, and HTML files outside the repo
   unless the user explicitly asks for a committed example.

Minimum information contract for every chart:

- clear title stating exactly what is compared;
- frequency and period;
- primary source/curation: `Dados Financeiros Abertos (openfindata)`;
- extraction timestamp in BRT;
- effective data cutoff: first and last date actually plotted;
- original source subsets/series identifiers, such as `BCB SGS 432` or
  `B3 IndexStatisticsProxy`;
- final technical line with audit data path, script/route path, renderer, and
  relevant transformations;
- audit data saved next to the visual artifact for one-off work.

Dependency and renderer policy:

- Do **not** add plotting libraries such as matplotlib, seaborn, plotly, altair,
  bokeh, or pandas as project dependencies just to make a chart.
- Prefer dependency-light outputs: tidy CSV plus hand-authored SVG or
  single-file HTML/inline SVG.
- PNG is acceptable for screenshot/raster delivery, but keep the CSV/script so it
  is not the only artifact.
- TradingView Lightweight Charts is the interactive Chart Lab renderer and the
  canonical visual/informational reference. Use it for interactive HTML when it
  helps, not as a universal obligation.
- If HTML/Lightweight Charts is used, keep attribution/copyright behavior aligned
  with `docs/CHART_STANDARDS.md` and the visible footer/link pattern.

Use the Chart Lab color tokens consistently:

- text principal: `#07132c`;
- juros/macro: orange `#ff7a1a`;
- mercado/B3: blue `#0050ff`;
- fonte/validação: green `#00a859`.

See `docs/CHART_STANDARDS.md` for the detailed specification, renderer decision
matrix, templates, and examples of source/technical lines.

## Release and handoff guardrails

- Do not publish to PyPI without explicit human approval.
- Do not tag a release until tests and adversarial review are clean.
- When handing off to another agent, summarize: what changed, why, verification,
  risks, and the next executable step.
