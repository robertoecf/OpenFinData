# MCP surface: curated tools over the REST API

> Status: prototype / design proposal (alpha 0.3.x). Non-breaking: the REST API
> is untouched. Implemented in [`src/findata/api/mcp_app.py`](../src/findata/api/mcp_app.py).

## Problem

The MCP server used to be auto-generated **1:1 from the FastAPI app**:
`FastApiMCP(app)` turns every route into a tool, so the catalog was **95 tools**,
one per dataset/endpoint. From a client/agent's point of view that means:

- **~21k tokens of `tools/list`** loaded at the start of every session, before a
  single call.
- **Worse tool selection**, a model picks worse among 95 near-duplicate names
  (one tool per SGS series, per CVM fund facet…) than among ~two dozen
  well-described tools.

## Approach (A + B + C)

A separate FastAPI app, `mcp_app`, is the **only** source of the tool catalog.
It exposes a small, hand-curated set of tools that dispatch to the same
`findata.sources.*` functions the REST routers already use.

```python
# app.py: tools come from mcp_app; transport is served on the public app
_mcp = FastApiMCP(mcp_app, name=..., description=...)
_mcp.mount_http(router=app)   # /mcp on the public app; REST routes untouched
```

`FastApiMCP(mcp_app)` builds the catalog from `mcp_app`'s OpenAPI and executes
each tool via `httpx.ASGITransport(app=mcp_app)`. Because the routers carry no
app-state/rate-limiter coupling, reusing the source functions in a second app is
safe. **The 95 REST routes that back the CLI and HTTP consumers never change.**

- **A, curation.** Each tool has an explicit `operation_id`, an agent-oriented
  one-line `summary`, and a docstring written *for an agent deciding whether to
  call it*, not the raw route docstring. `response_model=None` + `-> Any` keeps
  response schemas out of the catalog (they would re-inflate it).
- **B, consolidation.** Sprawly clusters collapse behind a `dataset`/`kind`
  selector (see table). The work moves from "many thin tools" to "few tools with
  good docs".
- **C, code mode.** One optional tool, `findata_run_code`, runs a Python
  snippet against the `findata` library in an isolated child interpreter. It
  replaces dozens of fine-grained calls for filter/join/aggregate flows that
  would otherwise stream every intermediate result through the model's context.
  **Gated off by default** (`FINDATA_MCP_CODE_MODE=1` to enable).

## Result

| | 1:1 (old) | curated (new) |
|---|---:|---:|
| MCP tools | 95 | **24** (25 with code mode) |
| `tools/list` size | ~85k chars (~21k tok) | **~29k chars (~7k tok)** |
| REST operations | 95 | **95 (unchanged)** |

## The 24 curated tools

```
registry_lookup          ← start here: CNPJ / ticker / code / name → entities

bcb_series   bcb_ptax   bcb_focus                       (BCB: 12 → 3)
cvm_company  cvm_financials  cvm_fund  cvm_structured_fund   (CVM: 22 → 4)
b3_quote  b3_cotahist  b3_index                          (B3: 9 → 3)
tesouro_bonds  tesouro_siconfi                           (Tesouro: 6 → 2)
ibge_indicator  ibge_ipca_breakdown                      (IBGE: 4 → 2)
ipea_series  ipea_search                                 (IPEA: 4 → 2)
anbima                                                   (ANBIMA: 3 → 1)
openfinance_directory                                    (Open Finance: 15 → 1)
basedosdados_search  basedosdados_sql                    (BdD: 7 → 2)
receita_arrecadacao   aneel_leiloes   susep_empresas
findata_run_code                                         (code mode, opt-in)
```

### Consolidation map

| Tool | Folds in | Selector |
|---|---|---|
| `bcb_series` | `/series`, `/series/code/{code}`, `/series/name/{name}` | `code` / `name` / none=catalog |
| `bcb_ptax` | `/ptax/usd`, `/ptax/usd/period`, `/ptax/{currency}` | `start`+`end` → period |
| `bcb_focus` | `/focus/{indicators,annual,monthly,selic,top5}` | `horizon`, `panel`, `indicator` |
| `cvm_company` | companies search/list, `fca/*`, `ipe` | `dataset=search\|list\|fca_*\|filings` |
| `cvm_fund` | `funds`, `funds/{daily,holdings,lamina,profile,periods}`, returns | `dataset` |
| `cvm_structured_fund` | `funds/{fii,fidc,fip}/*` | `kind` + `dataset` |
| `b3_index` | index portfolio + monthly + list | `dataset`, omit `symbol` to list |
| `tesouro_bonds` | bonds list/search/history | `dataset` |
| `tesouro_siconfi` | `rreo`, `rgf`, `entes` | `report` |
| `openfinance_directory` | participants/endpoints/resources/roles | `dataset` |

## Tradeoffs

- **Fewer but "fatter" tools.** Each carries a `dataset` enum and more doc. The
  whole bet is that good descriptions beat tool count, so the docstrings are the
  deliverable, not an afterthought.
- **Consolidation can hide endpoint-specific params behind an enum.** Mitigated
  by documenting each `dataset`/`kind` value and validating bad combinations with
  a `400` (e.g. `cvm_fund dataset=holdings` requires `cnpj`+`month`), matching the
  REST API's `ValueError → 400` behaviour.
- **Discoverability of rare endpoints.** A handful of niche REST routes are not
  individually surfaced as tools. They remain fully reachable over REST and via
  `findata_run_code`.

## Code mode: security

`findata_run_code` is a **prototype, not a hardened sandbox**. The snippet runs
in a child `python -I` (isolated mode, cwd in a tempdir) with a wall-clock
timeout and a 20k-char output cap, but it has full library and network access.
It is **disabled unless `FINDATA_MCP_CODE_MODE=1`** and is intended for trusted,
local/agent use. A production deployment should run it in a real sandbox
(container/seccomp/network egress controls) before enabling.

## Example flows (verified through the curated MCP)

- `registry_lookup(q="PETR4")` → PETROBRAS, CNPJ `33.000.167/0001-01`, `[PETR3, PETR4]` (offline).
- `bcb_ptax(start=2024-01-02, end=2024-01-05)` → daily PTAX USD series (the handoff's headline flow).
- `findata_run_code("import findata; ...")` → runs in the sandbox, returns captured stdout.
