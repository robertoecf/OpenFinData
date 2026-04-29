# AGENTS.md — findata-br

This file is for coding agents working in this repository. Keep it practical:
follow the project conventions, avoid speculative dependencies, and produce
reproducible data work.

## Project baseline

- Canonical working directory: the repository root, i.e. the directory that
  contains this `AGENTS.md`.
- Package: `findata-br`, a Python library + REST API + MCP server + CLI for
  Brazilian public financial data.
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
.venv/bin/ruff check src/ tests/ scripts/
.venv/bin/python -m mypy src/findata
.venv/bin/python -m pytest tests/ -q
```

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

## Graphics and chart generation standards

Agents will sometimes use this repo to generate exploratory charts for users.
Those charts should be clear, source-backed, and reproducible without turning the
library into a plotting package.

### Dependency policy

- Do **not** add plotting libraries such as matplotlib, seaborn, plotly, altair,
  bokeh, or pandas as project dependencies just to make a chart.
- Prefer no-library outputs when possible:
  1. CSV data export.
  2. Hand-authored SVG using Python standard library string templates or
     `xml.etree.ElementTree`.
  3. Single-file HTML with inline SVG when interactivity or browser rendering is
     useful.
- If a one-off local script uses a plotting library already installed on the
  machine, keep that script and its PNG/SVG outputs outside the repo unless the
  user explicitly asks to add an example.
- If a chart becomes a committed example, keep it dependency-light and place
  reusable code under `examples/` or docs assets only after confirming scope.

### Reproducibility contract

Every generated chart should make it possible to audit the result later:

- Save or print the exact script path, data path, and output path.
- Export the tidy source data as CSV next to the image for one-off work.
- Use `findata-br` APIs/CLI for data retrieval instead of ad hoc scraping when
  this repo already exposes the dataset.
- Include source names and series identifiers in the subtitle or footer, for
  example `BCB SGS 432` or `B3 IndexStatisticsProxy`.
- Include the consultation date or data cutoff date. Prefer ISO dates in file
  metadata and human labels in pt-BR (`Consulta em 2026-04-29`).
- Do not interpolate, forward-fill, or resample silently. State the frequency and
  transformation in the subtitle: monthly, daily close, 12-month sum, end-of-month,
  forward-filled policy rate, etc.

### Visual style

Default chart style for financial/economic time series:

- Canvas: 16:9 or wide report format. Good defaults: `1600x900` or SVG
  `viewBox="0 0 1600 900"`.
- Background: white or near-white (`#ffffff` / `#f8fafc`).
- Text color: dark slate (`#111827` for titles, `#4b5563` for secondary text).
- Grid: light horizontal grid only (`#e5e7eb`), no heavy chart junk.
- Borders/spines: thin and low-contrast (`#d1d5db`) or omitted.
- Typography: system sans-serif stack (`Inter`, `SF Pro`, `Segoe UI`, `Arial`,
  `sans-serif`). Title should be bold and larger than every other label.
- Use line widths thick enough for screenshots (`3px` to `5px` in SVG).
- Use color intentionally and consistently:
  - BCB / interest-rate series: orange `#d97706`.
  - B3 / equity-index series: blue `#2563eb`.
  - Neutral comparison: slate `#64748b`.
  - Negative or warning: red `#dc2626`.
- Do not rely on color alone. Use legend labels, direct labels, or line style
  differences where possible.

### Axes, labels, and formatting

- Titles should say exactly what is compared: `Selic meta vs Ibovespa`.
- Subtitles should include frequency, date range, and source mapping:
  `Dados mensais: jan/2016 a abr/2026. Selic = BCB SGS 432; Ibovespa = B3.`
- Axis labels must include units:
  - `Selic meta (% a.a.)`
  - `Ibovespa (mil pontos)`
  - `Valor (R$ bilhões)`
  - `Variação (% a.m.)`
- Prefer pt-BR month labels in user-facing charts: `jan/2026`, `abr/2026`.
- Use Brazilian numeric conventions in annotations when the output is for a
  Brazilian audience: decimal comma in prose, `R$`, `% a.a.`, `% a.m.`.
- Dual axes are acceptable only for unlike units. If used, color each axis label
  and tick labels to match its series, and mention both units in the legend.
- For policy rates such as Selic meta, prefer a step line when the data changes
  discretely. For market indexes, prefer a continuous line.
- Bars should normally start at zero. Line charts may use a narrowed y-axis, but
  the scale must remain visible and honest.

### Annotations and footers

- Add a compact final-value annotation when it improves readability, e.g.
  `Último ponto (abr/2026): Selic 14,75% a.a. | Ibovespa 188.619 pts`.
- Footer should include sources and consultation date, not generic claims.
- Keep legends inside unused whitespace or above the plot; avoid covering data.
- Avoid decorative logos, watermarks, shadows, gradients, and 3D effects unless
  explicitly requested.

### File naming and placement

For one-off user-requested graphics, prefer a temporary work directory outside
this repo and use snake_case names:

```text
selic_meta_vs_ibovespa.py
selic_meta_vs_ibovespa_mensal.csv
selic_meta_vs_ibovespa.svg
selic_meta_vs_ibovespa.png   # optional, only if specifically needed
```

Only commit chart artifacts when they are part of documented examples or a docs
page. If committed, include the script or generation instructions next to the
artifact so future agents can regenerate it.

## Release and handoff guardrails

- Do not publish to PyPI without explicit human approval.
- Do not tag a release until tests and adversarial review are clean.
- When handing off to another agent, summarize: what changed, why, verification,
  risks, and the next executable step.
