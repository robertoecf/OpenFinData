# `resolve_asset` — classificador de ativos (taxonomia Wealthuman)

> Entrega para o demandante (Wealthuman / consolidação de extratos). Define o
> contrato que o consolidador chama por ativo (dezenas por extrato). Implementado
> em [`src/findata/resolver/`](../src/findata/resolver/), exposto por REST, MCP e
> biblioteca Python.

## Problema

A consolidação classifica cada ativo na taxonomia macro do banker. O agente
antigo buscava ANBIMA/debentures.com.br no brave: lento e errava (chutava RV pelo
"11" de um ETF de debênture, perdia mandato global sem "IE", confundia "Crédito
Estruturado" com COE). `resolve_asset` devolve a classificação **determinística,
cacheável e auditável**, já na taxonomia do cliente.

## Como chamar

Três superfícies, mesmo núcleo:

| Superfície | Chamada |
|---|---|
| REST | `GET /resolver/resolve?ticker=IFRA11&name=FI%20ITAUINFRA` |
| MCP | tool `resolve_asset` (args `name`/`ticker`/`cnpj`/`isin`) |
| Python | `await findata.resolver.resolve_asset(ticker="IFRA11")` |

**Input** — qualquer subconjunto de identificadores; o resolver normaliza e
promove um identificador "pelado" passado em `name` (o extrato às vezes só tem o
label):

```json
{ "name": "FI ITAUINFRA CI", "ticker": "IFRA11", "cnpj": null, "isin": null }
```

Sem PII: o resolver recebe **só** identificador de ativo, nunca dado de cliente.
Limites de tamanho no boundary (`name` 256, `ticker` 16, `cnpj` 32, `isin` 16).

## Contrato de saída

```jsonc
{
  "identifier_resolved": { "cnpj": null, "ticker": "IFRA11", "isin": null, "name": "FI ITAUINFRA CI" },
  "kind": "etf",                     // fundo|acao|fii|etf|bdr|debenture|cra|cri|cdb|lci_lca|tesouro|coe|outro
  "cvm": { "classe": null, "anbima_categoria": null, "estrutura": "ETF" },
  "macro_class": "Renda Fixa",       // CLASSE DE ATIVO (ver eixo 1 abaixo)
  "subclasse": "Indexada à Inflação",
  "exposure": "Brasil",              // GEOGRAFIA (ver eixo 2) — Brasil|Internacional|null
  "underlying_nature": "debentures", // acoes|debentures|credito|recebiveis|imoveis|multiativos|tesouro|cambio|private_equity|outro
  "debenture": {                     // só quando há debênture
    "incentivada_1243": true,
    "lei_12431_status": "confirmed", // confirmed|candidate|not_applicable|unknown
    "indexador": "IPCA+",
    "vencimento": null
  },
  "tax": { "isento": true, "isento_status": "confirmed_exempt" },
  "source": "openfindata",           // openfindata|maisretorno|cvm|b3|web_search
  "confidence": 0.97,                // 0..1; baixa => human-in-the-loop
  "as_of": "2026-06-29",             // carimbado em America/Sao_Paulo
  "cascade": ["openfindata:curated"],// trilha de fontes percorrida
  "signals": [                       // trilha estruturada: que regra disparou e com qual evidência
    { "rule": "curated_seed", "evidence": "ticker=IFRA11", "detail": null }
  ],
  "notes": "Curated: ETF de debêntures de infraestrutura (FI-Infra, Lei 12.431)…"
}
```

### Dois eixos ortogonais (decisão de modelo)

1. **`macro_class` = classe de ativo**: `Renda Fixa`, `Renda Variável`,
   `Multimercado`, `Alternativos`, `Estruturados` (+ `Indefinido` quando o
   resolver não decide). Geografia **não** é valor de macro.
2. **`exposure` = geografia/estratégia**: `Brasil` | `Internacional` | `null`. É
   onde a exposição econômica está, independente da classe. A B3 é o domicílio do
   ativo, não a exposição. Logo:
   - **IVVB11** (ETF de S&P 500 listado na B3) → `RV` + `exposure=Internacional`
   - **BDR** → `RV` + `exposure=Internacional` (risco cambial/exterior)
   - **FIA de mandato global** (ARBOR, WHG) → `RV` + `exposure=Internacional`

### Eixo de certeza fiscal

Os bools `incentivada_1243`/`isento` respondem "sim/não". Os status carregam a
**certeza** que o bool não carrega:

- `lei_12431_status`: `confirmed` (sinal explícito de infra / FI-Infra),
  `candidate` (heurística emissor+IPCA, **confirmar por ISIN** antes de tratar
  como isento), `not_applicable` (é debênture, mas não infra), `unknown`.
- `isento_status`: `confirmed_exempt` (estatutário: CRA/CRI, LCI/LCA, 12.431
  confirmada), `candidate_exempt` (heurística), `confirmed_taxable`, `unknown`.

Quando `confidence < ~0.9` ou status `candidate`, é gancho de revisão humana.

## Cascata de fontes (fallback)

1. **openfindata** (primário, offline): seed curado + regras estruturais. Resolve
   o test set sem rede.
2. **Mais Retorno MCP** (dados BR de fundo/CNPJ/classe CVM).
3. **outro provider** (CVM dados abertos / B3).
4. **web_search restrito** a `maisretorno.com`, `b3.com.br`,
   `yahoofinance.com.br`, `debentures.com.br`.

Cada degrau preenche o que o anterior não trouxe e **baixa a confidence**;
`source` reflete a origem final; `cascade` loga o caminho. Os degraus 2 a 4 são
um ponto de extensão injetável (`AssetProvider`), consultado só quando o
resultado do núcleo está fraco. No estado atual deste PR, **só o degrau 1 está
ligado** (os externos são stubs a conectar no deploy).

## Test set (passa 100%, offline)

| Identificador | macro_class | exposure | nota |
|---|---|---|---|
| IFRA11 / FI ITAUINFRA | Renda Fixa | Brasil | ETF de debêntures de infra; "Indexada à Inflação"; isento confirmado |
| ARBOR FIC FIA | Renda Variável | Internacional | mandato global sem "IE" |
| WHG GLOBAL FIC FIA IE | Renda Variável | Internacional | estrutura IE |
| DEB PETROBRAS IPCA+ | Renda Fixa | Brasil | debênture; incentivada **candidate** (confirmar ISIN) |
| COE | Estruturados | (n/a) | `kind=coe`, **nunca** ETF |
| "Crédito Estruturado" (Warren/AMW) | Renda Fixa | Brasil | name-trap: é crédito, não Estruturados |
| IVVB11 | Renda Variável | Internacional | ETF de ações S&P 500 |
| HGLG11 / MXRF11 | Renda Variável | Brasil | subclasse FII |

## Não-funcionais

- **Determinístico + cacheável**: mesmo identificador → mesma classificação
  (exceto `as_of`); CNPJ/ticker mudam de classe raramente, cachear agressivo.
- **Latência baixa**: núcleo é offline, sem I/O.
- **Auditável**: sempre `source` + `as_of` + `cascade` + `signals`.
- **Sem PII**: só identificador de ativo cruza o boundary.

## Pendências antes de produção

- Conectar os providers externos reais (Mais Retorno MCP, web search restrito).
- Confirmação ISIN-level da incentivada (12.431) via ANBIMA/debentures.com.br no
  degrau de cascata — hoje fica `candidate`.
- Ampliar o seed curado de ETFs conforme novos ETFs forem listados na B3.
