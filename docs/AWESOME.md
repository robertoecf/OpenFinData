# Awesome adjacent platforms

Curated list of financial-data products evaluated as references for
Dados Financeiros Abertos. Not an endorsement. Not a source catalog.

Rule: study public product behavior. Do not scrape HTML as a core adapter. Do
not copy brand, copy, or private APIs. Official public sources stay primary.

Consulta desta revisão: 2026-09-04.

## How to read a row

| Field | Meaning |
|---|---|
| Fit | What this repo can learn without becoming the other product |
| Adapter | Whether a `findata.sources.*` module is justified |
| Agent | Machine-readable surface a local operator can bring |

Scores are 1–5, qualitative. Re-score when the public surface changes.

## Evaluated

| Platform | Role | UX ref | Agent | Adapter | Notes |
|---|---|---|---|---|---|
| [ETF1](https://etf1.com.br) | BR ETF/terminal + paid OnePro | 5 | 4 | no | Free product is the strongest BR ETF analysis UI seen. Paid MCP (`onepro:read`). Survey: [`ETF1_SURVEY.md`](ETF1_SURVEY.md). Ref: [`ETF1_PRODUCT_REF.md`](ETF1_PRODUCT_REF.md). |
| [OBM](https://obm.com.br) | BR cross-asset portal | 4 | 2 | no | Broad taxonomy, private REST by invite. Survey: [`OBM_API_SURVEY.md`](OBM_API_SURVEY.md). Ref: [`OBM_REVERSE_ENGINEERING.md`](OBM_REVERSE_ENGINEERING.md). |
| [Mais Retorno](https://maisretorno.com) | Commercial BR fund/asset API + MCP | 3 | 5 | optional cascade | Free logged-in quota. Resolver degrau 2, stubs today. [`RESOLVER.md`](RESOLVER.md), [`SOURCES_WITH_AUTH.md`](SOURCES_WITH_AUTH.md). |
| [ADVFN](https://br.advfn.com) | Unofficial statements HTML | 2 | 1 | no | Cloudflare-gated, stale scrapers. [`source-notes/advfn.md`](source-notes/advfn.md). |
| [justETF](https://justetf.com) | EU/global ETF product ancestor | 5 | 1 | no | Style box, domicile, TER, UCITS vs local listing. UX lineage for ETF1, not a BR source. |
| [OpenBB](https://github.com/OpenBB-finance/OpenBB) | Open data platform | 3 | 5 | no | Architecture peer (lib + REST + CLI + MCP). [`ROADMAP.md`](../ROADMAP.md). |

## ETF1 one-liner (2026-09-04)

Stop Loss Club / IBEE (CNPJ 58.095.342/0001-12). Free Next.js terminal for
ETFs (B3, US, Ireland) plus stocks, BDRs, FIIs, funds, FI-Infra, FI-Agro,
debentures and Tesouro. OnePro R$ 57,90/mês or R$ 499/ano (launch promo).
Public `llms.txt` plus OAuth 2.1 MCP for subscribers. No anonymous REST data
API. Use as product reference; do not add a source adapter.

## Adding a platform

1. Public pages, `robots.txt`, `llms.txt`, FAQ, pricing, and advertised
   machine surfaces only.
2. Write a survey note and, if the UI teaches something, a product-ref note
   with the same boundary as the OBM ref.
3. Add one row here. Link the notes. Do not implement an adapter in the same
   change unless official public data is missing and the vendor surface is
   licensed for that use.
