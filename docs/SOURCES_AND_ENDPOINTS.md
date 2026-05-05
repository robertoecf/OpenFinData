# Fontes e endpoints

Esta página concentra o detalhe operacional que saiu do README: fontes, famílias
de endpoints, notas de autenticação e exemplos mínimos de consulta.

Para testar interativamente, rode `findata serve` e abra `/api/docs` ou `/redoc`.

## Mapa de fontes

| Fonte | Cobertura principal | Endpoints principais | Autenticação |
|---|---|---|---|
| BCB SGS | Selic, CDI, IPCA, IGP-M, câmbio, PIB, desemprego e séries temporais SGS | `/bcb/series`, `/bcb/series/code/{code}`, `/bcb/series/name/{name}` | Não |
| BCB PTAX | Cotações oficiais de moedas | `/bcb/ptax/usd`, `/bcb/ptax/usd/period`, `/bcb/ptax/{currency}`, `/bcb/currencies` | Não |
| BCB Focus | Expectativas de mercado | `/bcb/focus/indicators`, `/bcb/focus/annual`, `/bcb/focus/monthly`, `/bcb/focus/selic`, `/bcb/focus/top5` | Não |
| Base dos Dados | Catálogo público, datasets gratuitos e consultas SQL via BigQuery | `/basedosdados/info`, `/basedosdados/search`, `/basedosdados/direct-download/free`, `/basedosdados/datasets`, `/basedosdados/tables`, `/basedosdados/columns` | Gratuito com login/projeto BigQuery para SQL |
| CVM | Companhias, DFP/ITR, IPE, FCA, fundos, CDA, lâmina, perfil, FII, FIDC e FIP | `/cvm/companies`, `/cvm/financials/dfp`, `/cvm/financials/itr`, `/cvm/companies/ipe`, `/cvm/funds`, `/cvm/funds/holdings`, `/cvm/funds/lamina`, `/cvm/funds/profile` | Não |
| Tesouro | Tesouro Direto e dados SICONFI | `/tesouro/bonds`, `/tesouro/bonds/search`, `/tesouro/bonds/history`, `/tesouro/siconfi/rreo`, `/tesouro/siconfi/rgf`, `/tesouro/siconfi/entes` | Não |
| IBGE | Indicadores econômicos, IPCA e grupos/subitens | `/ibge/indicators`, `/ibge/indicators/{name}`, `/ibge/ipca/breakdown`, `/ibge/ipca/groups` | Não |
| IPEA Data | Catálogo e séries macroeconômicas OData | `/ipea/catalog`, `/ipea/search`, `/ipea/series/{sercodigo}`, `/ipea/metadata/{sercodigo}` | Não |
| Open Finance Brasil | Diretório público, participantes, recursos, JWKS e Portal de Dados | `/openfinance/resources`, `/openfinance/participants`, `/openfinance/endpoints`, `/openfinance/directory/api-resources`, `/openfinance/portal/datasets` | Não para dados públicos |
| B3 | Cotações, COTAHIST oficial e composição teórica de índices | `/b3/quote/{ticker}`, `/b3/history/{ticker}`, `/b3/quotes`, `/b3/cotahist/year/{year}`, `/b3/indices`, `/b3/indices/{symbol}` | Não |
| Yahoo Finance | Endpoint experimental de gráfico de preços | `/yahoo/chart/{symbol}` | Não; fonte não oficial |
| ANBIMA | IMA, ETTJ e debêntures via arquivos públicos | `/anbima/ima`, `/anbima/ettj`, `/anbima/debentures` | Não para os arquivos usados |
| Receita Federal | Arrecadação por período, UF e tributo | `/receita/arrecadacao`, `/receita/tributos` | Não |
| ANEEL | Leilões de geração e transmissão | `/aneel/leiloes/geracao`, `/aneel/leiloes/transmissao` | Não |
| SUSEP | Entidades supervisionadas | `/susep/empresas`, `/susep/empresas/search` | Não |
| Registro | Resolvedor offline CNPJ, ticker, cod_cvm e nome | `/registry/lookup`, `/registry/meta` | Não; offline |
| Meta/MCP | Metadados, saúde, estatísticas e servidor MCP | `/meta`, `/health`, `/stats`, `/mcp` | Não |

## Exemplos REST

```bash
curl 'http://localhost:8000/bcb/series/name/selic?n=5'
curl 'http://localhost:8000/bcb/focus/annual?indicator=IPCA&top=3'
curl 'http://localhost:8000/cvm/companies/search?q=petrobras'
curl 'http://localhost:8000/cvm/funds/daily?cnpj=00.280.302/0001-60&limit=5'
curl 'http://localhost:8000/b3/quote/PETR4'
curl 'http://localhost:8000/b3/cotahist/year/2025?limit=5'
curl 'http://localhost:8000/openfinance/participants?role=DADOS&limit=20'
curl 'http://localhost:8000/registry/lookup?q=PETR4'
```

## Exemplos CLI

```bash
findata bcb series
findata bcb get selic -n 10
findata bcb focus -i IPCA -n 5
findata tesouro search IPCA+
findata ibge ipca -n 6
findata ipea search desemprego
findata openfinance participants --role DADOS -n 20
findata cvm search Petrobras
findata b3 quote PETR4
findata anbima ima -i IMA-B
findata registry lookup "33.000.167/0001-01"
```

## Registro offline

O registro embarcado resolve identificadores de múltiplas fontes em uma única
consulta:

```python
from findata.registry import lookup

await lookup("33000167000101")
await lookup("33.000.167/0001-01")
await lookup("PETR4")
await lookup("9512")
await lookup("petrobras")
```

A base é SQLite/FTS5, embarcada no pacote e reconstruída pelo fluxo de release.

## Notas de autenticação e origem

### Base dos Dados

Base dos Dados é gratuita para acesso público, mas consultas SQL/Python/R via
BigQuery normalmente exigem login Google e um projeto de cobrança do próprio
operador. O projeto usa a variável abaixo para trabalho local:

```bash
export FINDATA_BD_BILLING_PROJECT_ID="seu-projeto-gcp"
findata basedosdados sql br_bd_diretorios_brasil municipio --limit 5
```

O projeto também aceita `BASE_DOS_DADOS_BILLING_PROJECT_ID` e
`GOOGLE_CLOUD_PROJECT` como fallback. Use Project ID, não o nome visual do
projeto.

### ANBIMA

O módulo atual usa arquivos públicos em `www.anbima.com.br/informacoes/*`
(XLS/CSV/TXT), não a API comercial autenticada Sensedia. Produtos autenticados
futuros devem seguir o padrão de `docs/SOURCES_WITH_AUTH.md` e nunca embutir
credenciais no repositório.

### Yahoo Finance

O endpoint `/yahoo/chart/{symbol}` é experimental e não oficial. Para produção,
prefira rotas oficiais expostas por B3, CVM, BCB, Tesouro, Open Finance e demais
fontes governamentais/regulatórias.
