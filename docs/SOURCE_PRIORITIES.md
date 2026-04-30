# Source integration priorities

This is the current short list for agent-facing source work.

## P0 — Yahoo Finance chart adapter

Implemented as experimental/unofficial market-price retrieval.

- Module: `src/findata/sources/yahoo/`
- CLI: `findata yahoo chart PETR4.SA --range 1mo --interval 1d`
- API: `GET /yahoo/chart/{symbol}?range=1mo&interval=1d`
- Source note: `docs/source-notes/yahoo.md`

Keep it dependency-light and best-effort. Do not add Yahoo API keys or RapidAPI
wrappers.

## P1 — Stale reference cleanup

Update stale external references as they appear in docs or registries:

- `brapi.ga` -> `brapi.dev`
- old Tesouro Direto JSON endpoint -> deprecated/410; prefer Tesouro
  Transparente CKAN
- `dados.gov.br` -> currently not simple-agent accessible in the tested paths
- Fazenda SP SOAP -> SSL-chain caveat for agents

## P2 — Tesouro Transparente CKAN helper

Add a small helper around the working CKAN API before scraping Tesouro Direto
HTML pages.

Suggested module:

```text
src/findata/sources/tesouro/ckan.py
```

Suggested functions:

```python
package_search(query: str)
get_dataset_resources(dataset_id: str)
```

## P3 — Source health command

Add an agent-oriented health probe:

```bash
findata sources check
findata sources check --json
```

It should report HTTP status, source type, and whether the source is currently
agent-friendly.

## ADVFN — investigated, defer adapter

ADVFN can expose useful financial-statement tables, including Brazilian pages,
but it is unofficial HTML, partly Cloudflare-gated, and the old public gist is
stale and not directly reusable. Keep it documented in
`docs/source-notes/advfn.md`; do not implement a source adapter until official
CVM/B3 coverage gaps justify it.
