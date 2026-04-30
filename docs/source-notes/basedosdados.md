# Base dos Dados source note

Status: supported as a free logged-in source.

## TL;DR — what this really adds

Base dos Dados does **not** replace findata-br's canonical official-source
adapters for BCB, CVM, IBGE, Tesouro, B3, ANBIMA or Receita. For series we
already expose directly, such as Selic, FX, IPCA, PIB, CVM funds or Receita
arrecadação, treat Base dos Dados as a convenience/fallback/join layer.

The real addition is access to a broad, BigQuery-native analytical layer:

1. **Large-table joins without local downloads** across public datasets.
2. **Microdata and treated datasets** that are not yet native findata-br
   sources, especially banking, rural credit, labor, fiscal spending, trade,
   company ownership and regional socioeconomic context.
3. **Fast exploration before implementation**: use SQL to validate whether a
   dataset deserves a dedicated official adapter.
4. **Direct-download discovery** for datasets Base dos Dados already marks as
   free downloadable.

High-value incremental areas are `estban`, `agencia`, `sicor`,
`oferta_publica_distribuicao`, `administradores_carteira`, `cnpj`, `caged`,
`rais`, `pnadc`, `pof`, `mides`, `licitacao_contrato`, `cartao_pagamento`,
`comex_stat`, `exportadoras_importadoras`, `censo_2022`, `adh`, `avs` and
`iptu`.

Decision rule: keep official adapters canonical; use Base dos Dados when the
value is joins, microdata scale, treated tables, or coverage not yet present in
findata-br.

Consulta em 2026-04-30 via:

```text
https://backend.basedosdados.org/search/?theme=economics&locale=pt
https://backend.basedosdados.org/search/?contains=direct_download_free&theme=economics&locale=pt
```

## Access model

Base dos Dados is not like ANBIMA's authenticated developer products. SQL,
Python and R access are free/self-serve, but BigQuery still requires the
operator's Google login and a billing project. BD Pro remains separate and must
be tagged `paid_logged_in`.

Operational rule for agents:

```bash
export FINDATA_BD_BILLING_PROJECT_ID="<google-cloud-project-id>"
.venv/bin/findata basedosdados query \
  'SELECT id_municipio, nome FROM `basedosdados.br_bd_diretorios_brasil.municipio` LIMIT 5'
```

BigQuery can bill by bytes processed. Start with small `LIMIT` queries and avoid
broad `SELECT *` scans over microdata tables unless the user explicitly accepts
the cost/quota risk.

## What the catalog exposes

The public catalog currently returns:

- `theme=economics`: 272 datasets.
- `theme=economics&contains=direct_download_free`: 44 datasets.

`direct_download_free` means Base dos Dados marks at least one free direct-download
surface for the dataset. SQL/Python/R access still goes through BigQuery unless
a download URL is resolved separately.

## High-priority datasets for findata-br

These are the datasets most relevant to economics, finance, financial markets,
and investment analysis. Prefer them before broad catalogue mirroring.

| Priority | Dataset slug | Dataset | Tables | Free direct download | Paid/pro surface | Why it matters |
|---|---|---:|---:|---:|---:|---|
| P0 | `taxa_selic` | Taxa Selic | 1 | yes | yes | Core risk-free/policy-rate series; useful for pricing, macro, and portfolio context. |
| P0 | `taxa_cambio` | Taxa de Câmbio | 1 | yes | yes | FX factor for assets, trade, inflation, and returns in BRL/USD. |
| P0 | `ipca` | Índice Nacional de Preços ao Consumidor Amplo (IPCA) | 4 | yes | yes | Official inflation anchor for real returns and macro analysis. |
| P0 | `ipca15` | IPCA-15 | 4 | yes | yes | Inflation preview / nowcasting input. |
| P0 | `inpc` | INPC | 4 | yes | yes | Wage/household inflation context. |
| P0 | `igp` | Índice Geral de Preços | 7 | yes | no | Market-contract inflation index family; rent and wholesale sensitivity. |
| P0 | `pib` | Produto Interno Bruto (PIB) | 7 | yes | no | Growth anchor for macro and asset-allocation context. |
| P0 | `fi` | Fundos de Investimento | 6 | yes | yes | CVM fund universe; direct investment/fund analytics relevance. |
| P0 | `administradores_carteira` | Administradores de Carteira | 3 | yes | yes | Regulated asset-management participants. |
| P0 | `oferta_publica_distribuicao` | Ofertas de distribuição de ações | 1 | yes | yes | Equity capital markets / public offering tracking. |
| P0 | `estban` | Estatística Bancária (ESTBAN) | 2 | no | yes | Banking activity, credit/deposits by geography/institution. |
| P0 | `agencia` | Agências Bancárias | 1 | no | yes | Banking footprint and access-to-finance mapping. |
| P0 | `sicor` | Microdados do Sistema de Operações do Crédito Rural e do Proagro | 10 | yes | yes | Rural credit microdata; relevant for agribusiness, credit, and risk. |
| P0 | `cnpj` | Quadros Societários CNPJ | 4 | no | yes | Company ownership/network context for issuers, counterparties, and corporate analysis. |
| P1 | `arrecadacao` | Resultado da Arrecadação Federal | 5 | yes | no | Fiscal revenue; complements Tesouro/Receita integrations. |
| P1 | `estoque_divida_publica` | Estoque da Dívida Pública | 1 | yes | no | Public debt stock; sovereign-risk and fixed-income context. |
| P1 | `public_finance` | OECD Public Finance Dataset | 1 | yes | no | Cross-country fiscal comparison. |
| P1 | `emendas_parlamentares` | Emendas Parlamentares | 1 | yes | yes | Fiscal/political allocation signal. |
| P1 | `mides` | Microdados de Despesas de Entes Subnacionais (MiDES) | 8 | yes | yes | State/municipal public spending microdata. |
| P1 | `licitacao_contrato` | Licitações e Contratos do Governo Federal | 8 | yes | yes | Procurement/contracting signal for public spending and suppliers. |
| P1 | `cartao_pagamento` | Cartão de Pagamento do Governo Federal | 3 | yes | yes | Public expenditure detail. |
| P1 | `comex_stat` | Comex Stat | 4 | no | yes | Trade flow and sector exposure. |
| P1 | `exportadoras_importadoras` | Empresas exportadoras e importadoras | 1 | no | yes | Company-level external-sector exposure. |
| P1 | `caged` | CAGED | 5 | yes | yes | Formal labor market; high-frequency macro signal. |
| P1 | `rais` | RAIS | 2 | no | no | Annual formal labor market; structural employment/wage analysis. |
| P1 | `pnadc` | PNAD Contínua | 13 | yes | no | Labor/income macro indicators. |
| P1 | `pnad` | PNAD | 2 | no | yes | Historical labor/household microdata. |
| P1 | `pof` | Pesquisa de Orçamentos Familiares | 16 | yes | yes | Household spending basket; inflation/consumption context. |
| P1 | `precos_combustiveis` | Preços de Combustíveis | 1 | no | yes | Energy prices and inflation/pass-through. |
| P1 | `br_sp_saopaulo_dieese_icv` | Índice do Custo de Vida (ICV) | 1 | yes | no | Cost-of-living comparison. |
| P1 | `ipp` | Índice de Preços ao Produtor | 6 | yes | no | Producer inflation and margin-pressure indicator. |
| P2 | `censo_demografico` | Censo Demográfico | 32 | yes | yes | Demographic denominator for regional markets. |
| P2 | `censo_2022` | Censo 2022 | 15 | yes | yes | Newest demographic baseline. |
| P2 | `adh` | Atlas do Desenvolvimento Humano | 3 | yes | no | Socioeconomic context for regional risk/opportunity analysis. |
| P2 | `avs` | Atlas de Vulnerabilidade Social | 1 | no | yes | Regional vulnerability and credit-risk context. |
| P2 | `indicador_nivel_socioeconomico` | Indicador Nível Socioeconômico (INSE) | 4 | yes | no | Regional socioeconomic proxy. |
| P2 | `mundo_bm_wdi` | World Development Indicators (WDI) | 5 | yes | yes | Cross-country macro and development comparison. |
| P2 | `pwt` | Penn World Tables | 1 | yes | no | Productivity/growth research. |
| P2 | `supply_chain` | Supply Chain | 6 | yes | yes | Supply-chain/infrastructure exposure. |
| P2 | `ppm` | Pesquisa Pecuária Municipal | 4 | yes | no | Agribusiness regional fundamentals. |
| P2 | `pevs` | Extração Vegetal e Silvicultura | 2 | yes | no | Forestry/agro regional fundamentals. |
| P2 | `production` | Crop and Livestock Production | 7 | yes | yes | Global agriculture comparison. |
| P2 | `iptu` | IPTU municipal datasets | 1 each | mixed | mixed | Real-estate/local tax base; useful but city-specific and duplicated by slug. |

## Relevant but lower-priority / watchlist

The economics catalog also includes many global or not-yet-table-backed sources
that are relevant conceptually, but should not block the Brazilian source
roadmap. Revisit these only for specific user demand or when Base dos Dados
publishes tables:

- `operacoes_tesouro_direto` — Tesouro Direto operations; currently 0 tables in
  the catalog response.
- `base_monetaria_papel_moeda_emitido` — monetary base; 0 tables.
- `financial_reforms` — global financial reforms; 0 tables.
- `financial_access_survey_fas` — IMF-style financial access; 0 tables.
- `macro_financial_dataset` — macro-financial dataset; 0 tables.
- `systemic_banking_crises` — banking crises; 0 tables.
- `global_debt_database_gdd` — global debt; 0 tables.
- `international_banking_statistics_ibs` — international banking; 0 tables.
- `real_effective_exchange_rates` — real effective exchange rates; 0 tables.
- `economic_policy_uncertainty_epu` and `world_uncertainty_index_wui` —
  uncertainty indexes; 0 tables.
- `baci`, `comtrade`, `directions_of_trade_statistics_dots`,
  `the_observatory_of_economic_complexity_oec` — global trade; 0 tables.
- `world_inequality_database`, `oecd_income_distribution_database_idd`,
  `standardized_world_income_inequality_database_swiid` — inequality; 0 tables.
- `open_corporates`, `orbis_amadeus`, `bloomberg_billionaires_index`,
  `forbes_real_time_billionaires` — corporate/wealth datasets; 0 tables.

## Implementation guidance

1. Do not mirror all 272 economics datasets into the core API.
2. Add thin curated helpers only when they materially complement official
   sources already in findata-br.
3. Prefer BigQuery SQL templates and documented examples for exploratory work.
4. Keep expensive microdata scans out of tests. Unit tests must mock network and
   must not hit BigQuery.
5. When adding a committed helper, include source slug, access class, and a tiny
   smoke-query example with `LIMIT`.

Example usage:

```text
findata basedosdados direct-download-free --theme economics
findata basedosdados query '<small SQL>' --max-rows 100
```

Do not add a committed adapter for BD Pro-only surfaces unless the user
explicitly asks and provides the entitlement context.
