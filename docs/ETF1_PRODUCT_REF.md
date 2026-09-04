# ETF1 as product reference

Consulta: 2026-09-04
Referência pública: https://etf1.com.br
Citação no repo: [`ROADMAP.md`](../ROADMAP.md) → Lessons from adjacent
projects (produto fechado).

## Boundary

Use ETF1 as a public product reference, not as source code or brand to copy.
Independently implementable patterns:

- information architecture of an ETF/asset terminal;
- which fields a detail page must carry to be decision-useful;
- analysis views (rolling windows, percentiles, Ulcer, monthly heatmap);
- extending a short ETF series with the target index plus the ETF fee;
- dual-currency (BRL/USD) and declared as-of dates;
- `llms.txt` as an agent entry point.

Do not copy proprietary code, visual identity, theme packs, copy, icons,
assets, private API responses, or authenticated MCP payloads. Do not register
an OAuth client against their MCP from this repo. Terms
(https://etf1.com.br/termos-de-uso, 6 Aug 2026) §09 forbid systematic
extract/scrape, unauthorized crawlers, commercial reuse, and reverse
engineering. `robots.txt` `use=reference` does not override that. This note
is a human-readable product reference from targeted public pages, not a
license to automate their site.

## Public product anatomy

### Shell

Four tools in the terminal chrome: Ativos, Portfolio, Comparador, Buscar.
Landing search resolves ticker, name or CNPJ without leaving `/`. Ticker tape
mixes B3, US and Irish tickers (`BOVA11`, `IVVB11`, `SPY`, `VWRA`, `CSPX`).
Theme switcher and UI scale (100/110/125) are product chrome, not a data
lesson.

### Detail page (example: `/etf/BOVA11`)

A complete ficha bundles what a resolver + CVM cadastro + CDA + B3 quote
already know in pieces:

1. Identity: ticker, exchange, ISIN, currency, domicile, inception.
2. Legal: CNPJ, gestor, admin, custodiante, auditor.
3. Economics: TER, AUM, dividend policy, index, category, number of holdings.
4. Style box (cap × value/blend/growth) and factor sliders.
5. Top holdings with sector and country.
6. AUM and shareholder count over time.
7. Returns in BRL and USD vs selectable benchmarks, 6m–max.
8. Similar ETFs.
9. Geo and sector weights.
10. Market-maker contracts (spread, size, hours).

Openfindata fit: identity and legal are CVM/B3/registry work. Holdings are
CDA. Returns need a normalized time-series adapter (already the OBM lesson).
Style box and factors are derived views, not a new source.

### Analysis page (example: `/etf/LVOL11/analise`)

The page that is worth stealing as *structure*, not pixels:

- user-set window and currency;
- “complementar com índice” plus an explicit fee field;
- percentile table of real returns by holding period (1y–20y);
- scoreboard vs benchmarks: CAGR, vol, best/worst year, max DD, Sharpe,
  Sortino, Ulcer;
- rolling-window win rate;
- distribution, accumulation, drawdown with recovery time;
- correlation matrix;
- monthly return heatmap vs IBOV, IDIV, IFIX, CDI, IPCA, CPI, S&P 500,
  IMA family.

The LVOL11 run used 2003–2026 after index complement. Any Chart Lab or demo
that copies this view must label reconstructed history as reconstructed.

### Portfolio and comparator

`/portfolio`: composition, 1995–2026, BRL/USD, process button.
`/comparador`: up to 10 assets or portfolios, shared window, same process
step. Deeper metrics than a simple rebase-from-date table.

### OnePro (paid; sales page only)

Five modules on the same database: allocation (explore / optimize /
behavior / multiperiod / prospective Monte Carlo), implementation
(index→product, synthetic `CDI+x` / `IPCA+x`), scoreboard, contribution
math, goal-based investing. Dual persona: investidor vs consultor/assessor.

This is adjacent to a planning product, not to an official-data library.
Do not port Monte Carlo or GBI into openfindata. If Wealthuman/Monvanti
need a cheap external bench, OnePro at R$ 57,90/mês is the current public
price anchor.

## What this repo already has

CVM funds/CDA/lâmina, B3 quotes and index composition, Tesouro, ANBIMA,
registry lookup, and a Chart Lab with an information contract. The gap is
packaging: no ETF ficha, no holdings view, no rolling-window/percentile
demo, no index-complement helper.

## What to implement here (in order)

Keep Python-first. No JS app as the first move.

1. **ETF ficha as API fields, not a page.** Resolve ticker → CNPJ, ISIN,
   gestor/admin, TER, index name, inception. Seed + CVM cadastro. Not a
   numbered item in `SOURCE_PRIORITIES.md` today (P2 there is Tesouro
   CKAN). Do not file it under an OBM backlog.
2. **Holdings view.** Latest CDA for ETFs, top-N + sector rollup. Public
   MCP already grew CDA; productize a stable response shape.
3. **Index complement helper.** Given ETF fee + official index series,
   splice pre-inception history and stamp `reconstructed=true`. Useful for
   `resolve_asset` notes and for Chart Lab caveats.
4. **Analysis contract in Chart Lab.** Percentiles, max DD, Ulcer, monthly
   heatmap only after a normalized return series exists. Reuse
   [`CHART_STANDARDS.md`](CHART_STANDARDS.md): as-of, source ids, no silent
   fill.
5. **`llms.txt` for this project.** ETF1 shows the agent-entry pattern:
   what the product is, which URLs to open, what it does not do (no
   real-time quotes, no recommendation). Cheap trust surface.

Skip: theme marketplace, terminal chrome, OnePro modules, scraping their
pages, bundling their MCP.

## Agent notes

Their `llms.txt` is the cleanest BR-finance agent doc seen in this sweep.
It states coverage, tool URLs, non-goals, and the paid MCP in one screen.
When openfindata publishes a public site, ship an equivalent file before
another landing redesign.

OnePro AI (privacy policy): subscriber connects Claude/ChatGPT; connector
is read-only on public asset data plus that user’s portfolios; cadastro and
payment stay off the wire. Irrelevant to this repo except as a reminder
that a paid MCP must not leak operator identity into examples.
