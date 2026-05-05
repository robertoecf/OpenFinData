# Padrão oficial de gráficos

Este padrão vale para gráficos gerados pelo Dados Financeiros Abertos,
incluindo páginas interativas, screenshots e artefatos avulsos.

## Identidade visual

- Fundo claro com glow discreto nas cores do projeto.
- Texto principal em `#07132c`.
- Azul de mercado: `#0050ff`.
- Laranja de juros/macroeconomia: `#ff7a1a`.
- Verde de fonte/validação: `#00a859`.
- Grade horizontal leve; evitar grade vertical e excesso de molduras.

## Metadados no topo

Todo gráfico deve mostrar, de forma visível no topo:

- `Fonte primária`: `Dados Abertos de Mercado (findata-br)`.
- `Extração`: timestamp da extração em BRT.
- `Recorte dos dados`: primeira e última data efetivamente plotadas.

## Fontes no rodapé

O bloco `Fontes dos dados` deve ficar abaixo do gráfico e acima da linha de
artefatos técnicos (`CSV auditável`, biblioteca de gráfico etc.).

Formato:

```text
Fontes dos dados. Fonte primária/curadoria:
Dados Abertos de Mercado (findata-br).
Subsets originais: <fonte id> para <série>; <fonte id> para <série>.
```

`Dados Abertos de Mercado (findata-br)` deve apontar para:

```text
https://github.com/robertoecf/findata-br
```

## Linha técnica final

A última linha deve ficar compacta:

- CSV auditável ou caminho de dados reproduzível.
- Biblioteca de visualização, se houver exigência de atribuição.

Quando usar TradingView Lightweight Charts com `attributionLogo: false`, manter
um link discreto para:

```text
https://www.tradingview.com/lightweight-charts/
```

## Regra de fonte primária

Para artefatos gerados pelo projeto, a fonte primária/curadoria é sempre o
Dados Abertos de Mercado (`findata-br`). As fontes externas aparecem como
subsets originais, com identificadores auditáveis, por exemplo:

- `BCB SGS 432` para Selic meta.
- `B3 IndexStatisticsProxy` para Ibovespa.
- `IBGE Agregados 7060/63` para IPCA mensal.
- `IPEA Data BM12_TJOVER12` para Selic over mensal.

## Reprodutibilidade

Todo gráfico exportado deve preservar:

- script ou rota usada para geração;
- CSV ou JSON base;
- timestamp de extração;
- recorte de dados;
- identificadores das fontes originais.
