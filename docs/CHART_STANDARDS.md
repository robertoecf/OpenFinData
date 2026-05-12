# Padrão oficial de gráficos

Este padrão vale para gráficos gerados pelo Dados Financeiros Abertos,
incluindo o Chart Lab (`/charts`), screenshots, SVG/PNG/HTML avulsos e qualquer
artefato criado por agentes a partir dos dados do projeto.

A regra central é simples: o Chart Lab com TradingView Lightweight Charts é a
referência visual e informacional canônica, mas o renderer não é obrigatório. O
mesmo contrato mínimo deve aparecer quando o resultado final for SVG, PNG, HTML
inline ou Lightweight Charts.

## Papel do Chart Lab

O Chart Lab é a referência de estrutura:

- cabeçalho com fonte/série, título e estado;
- bloco de metadados no topo;
- gráfico limpo com grade horizontal leve;
- bloco de fontes abaixo do gráfico;
- linha técnica final com dados auditáveis e renderer.

O produto principal continua sendo API REST, biblioteca Python, CLI e MCP. O
Chart Lab é uma vitrine experimental de visualização, não uma exigência para todo
script ou exemplo.

Presets públicos devem priorizar fontes oficiais/auditáveis já integradas no
projeto. Fontes experimentais ou indiretas, como Yahoo/yfinance, não entram na
vitrine principal.

## Contrato mínimo de informação

Todo gráfico precisa carregar, de forma visível ou em metadados diretamente
anexos ao artefato, os itens abaixo.

1. **Título claro**: dizer exatamente o que está sendo comparado ou medido, por
   exemplo `Selic meta vs Ibovespa`.
2. **Frequência e período**: informar a periodicidade e o intervalo apresentado,
   por exemplo `Dados mensais: jan/2016 a abr/2026`.
3. **Fonte primária/curadoria do repo**:
   `Dados Financeiros Abertos (findata-br)` apontando para
   `https://github.com/robertoecf/findata-br`.
4. **Extração**: timestamp da extração em BRT. Use formato explícito, por
   exemplo `2026-05-11 14:32:05 BRT` ou `11/05/2026, 14:32:05 BRT`.
5. **Recorte efetivo dos dados**: primeira e última data realmente plotadas após
   filtros, normalização, agregação ou perda de pontos, não apenas o período
   solicitado.
6. **Fontes originais/subsets**: identificadores auditáveis das fontes externas
   usadas, como `BCB SGS 432`, `B3 IndexStatisticsProxy`,
   `IBGE Agregados 7060/63` ou `IPEA Data BM12_TJOVER12`.
7. **Transformações**: frequência, agregação, reamostragem, preenchimento,
   normalização ou conversão de unidade. Não interpolar, forward-fill ou
   resamplear silenciosamente.
8. **Linha técnica**: caminho do CSV/JSON auditável, script/rota usada,
   renderer, versão/biblioteca quando relevante e contagem de pontos.
9. **Dados auditáveis**: em gráficos one-off, salvar o CSV/JSON de base junto do
   visual. Em páginas do projeto, expor o endpoint JSON ou caminho reproduzível.

## Anatomia recomendada

### Cabeçalho

- Rótulo curto da série/fonte principal, por exemplo `BCB SGS 432`.
- Título em destaque.
- Status ou observação curta quando o gráfico é interativo.
- Subtítulo com frequência, período e mapeamento de fontes quando couber.

Exemplo:

```text
Selic meta vs Ibovespa
Dados mensais: jan/2016 a abr/2026. Selic = BCB SGS 432; Ibovespa = B3.
```

### Metadados no topo

Todo gráfico deve mostrar ou anexar estes campos:

```text
Fonte primária: Dados Financeiros Abertos (findata-br)
Extração: 2026-05-11 14:32:05 BRT
Recorte dos dados: 2016-01-31 -> 2026-04-30
```

Se o usuário pediu um período diferente do recorte efetivo, explicite ambos:
`período solicitado` e `recorte efetivo`.

### Fontes no rodapé

O bloco `Fontes dos dados` deve ficar abaixo do gráfico e acima da linha técnica.

Formato recomendado:

```text
Fontes dos dados. Fonte primária/curadoria:
Dados Financeiros Abertos (findata-br).
Subsets originais: BCB SGS 432 para Selic meta; B3 IndexStatisticsProxy para Ibovespa.
```

A fonte primária deve apontar para:

```text
https://github.com/robertoecf/findata-br
```

### Linha técnica final

A última linha deve ser compacta e auditável:

```text
CSV auditável: ./selic_meta_vs_ibovespa_mensal.csv · Script: ./selic_meta_vs_ibovespa.py · Renderer: SVG stdlib · Pontos: 124 · Transformações: mês-fim, sem interpolação
```

Para páginas do próprio projeto, o caminho reproduzível pode ser um endpoint JSON
em vez de um CSV materializado:

```text
JSON auditável: /bcb/series/code/432?start=2024-05-11&end=2026-05-11 · Script: src/findata/web/static/chart-explorer.js · Renderer: TradingView Lightweight Charts 5.2.0
```

## Identidade visual

Use os tokens do Chart Lab como padrão visual:

- fundo: `#ffffff` ou near-white (`#f8fbff` / `#f8fafc`);
- texto principal: `#07132c`;
- texto secundário: `#42526f`;
- linha/borda: `rgba(7, 19, 44, 0.12)` ou `rgba(0, 39, 118, 0.16)`;
- grade horizontal: `rgba(0, 39, 118, 0.10)`;
- mercado/B3: blue `#0050ff`;
- juros/macro: orange `#ff7a1a`;
- fonte/validação: green `#00a859`;
- negativo/erro: red `#ef4444`.

Estilo padrão para séries financeiras/econômicas:

- canvas 16:9 ou formato largo. Bons defaults: `1600x900` ou SVG
  `viewBox="0 0 1600 900"`;
- tipografia system sans-serif (`Inter`, `SF Pro`, `Segoe UI`, `Arial`,
  `sans-serif`);
- título maior e bold;
- grade horizontal leve, sem grade vertical pesada;
- bordas/spines finas ou omitidas;
- linhas com espessura suficiente para screenshots (`3px` a `5px` em SVG);
- sem logos decorativos, watermarks, sombras, gradientes fortes ou 3D, salvo
  pedido explícito.

Não dependa apenas de cor. Use legenda, labels diretos, estilo de linha ou eixo
colorido quando houver mais de uma série.

## Eixos, labels e formatação

- Títulos devem dizer exatamente o que é comparado.
- Subtítulos devem incluir frequência, período e mapeamento de fontes.
- Labels de eixo precisam incluir unidade:
  - `Selic meta (% a.a.)`;
  - `Ibovespa (mil pontos)`;
  - `Valor (R$ bilhões)`;
  - `Variação (% a.m.)`.
- Preferir meses em pt-BR para gráficos voltados a público brasileiro:
  `jan/2026`, `abr/2026`.
- Usar convenções numéricas brasileiras em anotações: vírgula decimal, `R$`,
  `% a.a.`, `% a.m.`.
- Eixos duplos são aceitáveis apenas para unidades diferentes. Se usar dois
  eixos, colorir label e ticks com a cor da série e explicitar as unidades.
- Para taxas de política monetária, preferir linha em degrau quando a série muda
  discretamente. Para índices de mercado, preferir linha contínua.
- Barras normalmente começam em zero. Linhas podem usar eixo y estreito, desde
  que a escala fique visível e honesta.

## Escolha de renderer

O renderer é uma decisão operacional, não o padrão mínimo em si.

| Renderer | Quando usar | Requisitos |
| --- | --- | --- |
| SVG estático | Default para one-off auditável e sem dependências pesadas. | Salvar CSV/JSON base, script e SVG juntos. Usar tokens do Chart Lab. |
| PNG | Quando o usuário pede imagem raster, preview rápido ou screenshot. | Não entregar só PNG; manter CSV/JSON e script. Preferir gerar a partir de SVG/HTML reproduzível. |
| HTML inline/SVG | Quando interatividade leve, tooltip ou renderização em navegador ajuda. | Manter tudo em arquivo único quando possível; incluir fontes, metadados e linha técnica. |
| TradingView Lightweight Charts | Chart Lab, interatividade temporal rica, crosshair/zoom ou HTML interativo. | Não tratar como dependência universal. Manter atribuição e link visível conforme abaixo. |
| Bibliotecas locais de plotting | Apenas para script descartável fora do repo quando já disponíveis ou explicitamente aceitas. | Não adicionar como dependência do projeto só para gráfico; reportar dependências usadas. |

## TradingView Lightweight Charts

Quando usar Lightweight Charts com `attributionLogo: false`, manter o aviso de
copyright no código-fonte e um link visível para:

```text
https://www.tradingview.com/lightweight-charts/
```

Texto recomendado no rodapé da página:

```text
Gráfico: TradingView Lightweight Charts™
```

O uso de Lightweight Charts não dispensa o contrato mínimo: metadados, fontes,
recorte efetivo e linha técnica continuam obrigatórios.

## One-off chart runbook

Para pedidos simples como `gere um gráfico da Selic meta vs Ibovespa`:

1. Usar o repo como fonte de consulta quando a série já estiver exposta por API,
   CLI ou módulo Python. Não fazer scraping ad hoc se houver wrapper do projeto.
2. Se a fonte necessária ainda não estiver exposta, declarar o gap e registrar
   follow-up separado. Não misturar implementação de fonte nova com o gráfico.
3. Criar um diretório temporário fora do repo para artefatos descartáveis.
4. Salvar nomes em snake_case:

```text
selic_meta_vs_ibovespa.py
selic_meta_vs_ibovespa_mensal.csv
selic_meta_vs_ibovespa.svg
selic_meta_vs_ibovespa.png   # opcional, se raster for necessário
selic_meta_vs_ibovespa.html  # opcional, se HTML/interatividade for necessário
```

5. Exportar dados tidy com datas, valores já normalizados e colunas de origem
   suficientes para auditoria.
6. Gerar visual com o contrato mínimo completo.
7. Ao entregar, reportar script, dados, artefato visual, renderer, fontes e data
   de extração.

Só commitar artefatos de gráfico quando forem parte de exemplos/documentação
aprovados. Nesse caso, incluir script ou instruções de geração ao lado do
artefato para permitir regeneração.

## Regra de fonte primária

Para artefatos gerados pelo projeto, a fonte primária/curadoria é sempre o
Dados Financeiros Abertos (`findata-br`). As fontes externas aparecem como
subsets originais, com identificadores auditáveis, por exemplo:

- `BCB SGS 432` para Selic meta;
- `B3 IndexStatisticsProxy` para Ibovespa;
- `IBGE Agregados 7060/63` para IPCA mensal;
- `IPEA Data BM12_TJOVER12` para Selic over mensal.

Não inserir credenciais, tokens, caminhos privados de credenciais ou projetos de
billing privados em código, docs, exemplos ou artefatos gerados. Quando Base dos
Dados/BigQuery for usado, seguir o runbook de `AGENTS.md`.

## Reprodutibilidade

Todo gráfico exportado deve preservar:

- script ou rota usada para geração;
- CSV ou JSON base;
- timestamp de extração em BRT;
- período solicitado, quando relevante;
- recorte efetivo dos dados;
- frequência e transformações;
- identificadores das fontes originais;
- renderer e biblioteca/versão quando aplicável.
