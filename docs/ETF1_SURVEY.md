# ETF1: levantamento público

Consulta: 2026-09-04
Site: https://etf1.com.br
`llms.txt`: https://etf1.com.br/llms.txt
Privacidade: https://etf1.com.br/privacidade

## O que é

Portal de análise de ETFs (B3, EUA, Irlanda/UCITS) com terminal de ativos,
portfólio, comparador e busca. A landing e o JSON-LD declaram o produto
gratuito. OnePro é a camada paga de alocação, Monte Carlo e planejamento.

Mantenedor declarado: Stop Loss Club
(https://stoplossclub.com.br). Controlador LGPD: IBEE — Investimentos
Baseados em Evidências LTDA, CNPJ 58.095.342/0001-12, Vila Velha/ES.
Lançamento público do ETF1: abril/2026. OnePro: junho/2026.

## Cotação (tabela pública do OnePro)

Conferido em `/onepro` em 2026-09-04. Valores de lançamento, sem fidelidade,
cancelamento no painel, 7 dias de garantia.

| Plano | De | Por | Equivalente |
|---|---|---|---|
| OnePro mensal | R$ 77,90/mês | R$ 57,90/mês | — |
| OnePro anual | R$ 790,90/ano | R$ 499,00/ano | R$ 41,58/mês |

O núcleo (ficha de ativo, composição, análise, portfólio, comparador, busca)
permanece gratuito segundo a própria landing, o JSON-LD (`isAccessibleForFree`)
e o site do Stop Loss Club.

Não há tabela pública de API REST, créditos ou licença de dados. O MCP é
anunciado só para assinante OnePro.

## Superfície máquina (pública)

| Superfície | Status em 2026-09-04 | Nota |
|---|---|---|
| `GET /llms.txt` | 200 | Inventário de classes, rotas e MCP. Melhor doc de agente do site. |
| `GET /.well-known/oauth-authorization-server` | 200 JSON | Issuer `https://etf1.com.br/mcp`. Scope `onepro:read`. Authorization code + PKCE S256 + refresh + dynamic registration. |
| `https://etf1.com.br/mcp` | 405 em GET/HEAD | Compatível com MCP que só aceita POST. Não exercitado. |
| `GET /api`, `/docs`, `/developers`, `/faq`, `/sobre`, `/status`, `/metodologia` | 404 | Sem portal de desenvolvedor e sem FAQ/metodologia. |
| `GET /api/og` | 200 PNG | Gerador de Open Graph. Não é API de dados. |
| `GET /sitemap.xml` | 500 neste probe | `llms.txt` aponta o sitemap; a superfície de busca/IA está incompleta. |
| `GET /privacidade` | 200 | Controlador, PostHog, Google Ads, OnePro AI. |
| `GET /termos` | 404 | Linkado na privacidade; rota ausente. |
| HTML das páginas de produto | 200 | Next.js + Cloudflare. Cookie de interface `etf1_itk` (HttpOnly, 6h). |

Não registrar cliente OAuth, não chamar `/mcp/authorize` e não tratar o MCP
como fonte core. O operador que quiser o degrau pago usa a própria conta.

## Anatomia de produto (rotas públicas)

Inventário alinhado ao `llms.txt` e às páginas abertas:

| Rota | Papel |
|---|---|
| `/` | Landing com busca, PL do mercado B3, ranking de captação, lançamentos, comparativo global |
| `/etf`, `/acao`, `/bdr`, `/fii`, `/fundo-investimento`, `/fi-infra`, `/fi-agro`, `/debenture`, `/renda-fixa-publica`, `/renda-fixa-privada` | Listas por classe |
| `/etf/{ticker}` | Ficha: identificação, estrutura legal, style box, holdings, PL, retorno, similares, geo/setor, fatores, formadores |
| `/etf/{ticker}/composicao` | Holdings completas |
| `/etf/{ticker}/analise` | Janelas móveis, percentis, Sharpe/Sortino/Ulcer, drawdown, correlação, heatmap mensal |
| `/portfolio` | Simulação 1995–2026, BRL/USD |
| `/comparador` | Até 10 ativos, benchmarks, mesmo recorte |
| `/buscar` | Ticker, nome ou CNPJ |
| `/onepro` | Venda dos 5 módulos pagos |

Claims da landing (não auditados aqui): +8.000 ETFs; +1 milhão de holdings;
+125 mil produtos; mercado B3 com PL R$ 136 bi e 220 ETFs (jun/2026 na UI).
A análise de LVOL11 processou 01/2003–09/2026 via “complementar com índice”:
histórico reconstruído, não só a série própria do ETF.

## Stack visível no HTML/headers

Next.js (Turbopack, `x-nextjs-cache`), Cloudflare, Sentry, PostHog, Google
Ads, fonte Geist / JetBrains Mono, tema e escala de UI no `localStorage`.
Host de telemetria `e.etf1.com.br`. JSON-LD de `WebSite`,
`Organization` (parent Stop Loss Club) e `WebApplication` gratuita.

`robots.txt` (Cloudflare managed): `search=yes`, `ai-train=no`,
`use=reference`. Sitemap declarado.

## Leitura vs openfindata

| Eixo | ETF1 | openfindata |
|---|---|---|
| Natureza | Produto hospedado, educação + assinatura | Infra aberta (lib + REST + CLI + MCP) |
| API de dados anônima | Não encontrada | Sim |
| MCP | Pago, OAuth, `onepro:read` | Público (macro/CVM) + interno |
| ETF como produto | À frente (ficha, holdings, análise, UCITS) | Gap de visão de produto; CVM/B3 já cobrem parte do substrato |
| Fonte oficial | Declara órgãos públicos + snapshot mensal | Fonte oficial é o contrato |
| Self-host / MIT | Não | Sim |

Decisão: **não** criar `src/findata/sources/etf1/`. Tratar OnePro MCP como
possível degrau opcional no mesmo espírito da Mais Retorno (conta do
operador, nunca credencial no repo) só se um caso real exigir. Até lá, o
valor é referência de produto.

## Fosso

ETF1 vende convicção de alocação e uma ficha de ETF no nível justETF, com
B3 + US + UCITS na mesma UI. openfindata vende dado oficial reproduzível.
O overlap útil é taxonomia (ETF/BDR/FII/FI-Infra), holdings e a ideia de
estender histórico curto com o índice-alvo + taxa — implementável em cima
de CVM/B3/ANBIMA, sem o site deles.
