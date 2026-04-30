<!-- markdownlint-disable MD033 MD041 -->

```text
 ███████╗██╗███╗   ██╗██████╗  █████╗ ████████╗ █████╗        ██████╗ ██████╗
 ██╔════╝██║████╗  ██║██╔══██╗██╔══██╗╚══██╔══╝██╔══██╗       ██╔══██╗██╔══██╗
 █████╗  ██║██╔██╗ ██║██║  ██║███████║   ██║   ███████║ █████╗██████╔╝██████╔╝
 ██╔══╝  ██║██║╚██╗██║██║  ██║██╔══██║   ██║   ██╔══██║ ╚════╝██╔══██╗██╔══██╗
 ██║     ██║██║ ╚████║██████╔╝██║  ██║   ██║   ██║  ██║       ██████╔╝██║  ██║
 ╚═╝     ╚═╝╚═╝  ╚═══╝╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝       ╚═════╝ ╚═╝  ╚═╝

                   Dados financeiros abertos do Brasil
        BCB · CVM · B3 · IBGE · IPEA · Tesouro · Open Finance  →  API + MCP + CLI
```

<div align="center">

**API + servidor MCP + CLI de código aberto para dados financeiros brasileiros.**

_Agrega dados públicos de BCB, CVM, B3, IBGE, IPEA, Tesouro Nacional e Open Finance Brasil._
_De graça. Sem chave de API. Sem truques de limite de chamadas. Só Python._

<p>
  <a href="https://github.com/robertoecf/findata-br/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/robertoecf/findata-br/ci.yml?branch=main&label=CI&logo=github"></a>
  <img alt="Versão" src="https://img.shields.io/badge/versão-0.3.1--alpha-009c3b">
  <img alt="Python" src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue?logo=python&logoColor=white">
  <a href="https://github.com/robertoecf/findata-br/blob/main/LICENSE"><img alt="Licença MIT" src="https://img.shields.io/badge/licença-MIT-yellow.svg"></a>
  <img alt="Estado" src="https://img.shields.io/badge/status-alpha-orange">
</p>

</div>

---

## Resumo | TL;DR

O objetivo final do **findata-br** é se tornar a infraestrutura aberta de
referência para dados financeiros públicos do Brasil: uma camada confiável,
auditável e extensível que conecta fontes como BCB, CVM, B3, IBGE, IPEA,
Tesouro Nacional e Open Finance a bibliotecas, APIs, CLIs, agentes e
aplicações.

findata-br é uma biblioteca, API REST, servidor MCP e CLI para consultar dados
financeiros públicos do Brasil em um único lugar. Hoje cobre BCB, CVM, B3,
IBGE, IPEA, Tesouro Nacional, ANBIMA, Receita Federal, ANEEL, SUSEP e recursos
públicos do Open Finance Brasil. O projeto não exige chaves de API para as
fontes principais, não consulta dados privados de clientes e mantém integrações
reproduzíveis com testes sem rede.

Leia também: [MANIFESTO.txt](MANIFESTO.txt).


```text
                            ▌
▛▌  ▛▌▌▌█▌  ▌▌▛▌▛▘█▌  ▛▌▀▌▛▌▛▌▀▌
▙▌  ▙▌▙▌▙▖  ▚▘▙▌▙▖▙▖  ▙▌█▌▌▌▌▌█▌
     ▌                ▄▌

    O que você ganha
```

---


- **API REST** com Swagger interativo em `/docs`.
- **Servidor MCP** montado automaticamente em `/mcp` — plugue o findata-br direto no Claude, Cursor, Codex.
- **CLI Python** (`findata ...`) com tabelas ricas e banner animado em terminal interativo.
- **Biblioteca assíncrona** com reuso de conexões, retentativas com espera exponencial e cache LRU de 15 min.
- **Registro CNPJ ↔ ticker ↔ nome** embarcado no pacote wheel (~50k entidades CVM + SUSEP + B3) — uma consulta resolve qualquer formato.
- **Zero autenticação, zero chaves de API.** Todas as fontes são dados públicos governamentais.

```text
▐▘    ▗        ▌     ▌   ▌
▜▘▛▌▛▌▜▘█▌▛▘  ▛▌█▌  ▛▌▀▌▛▌▛▌▛▘
▐ ▙▌▌▌▐▖▙▖▄▌  ▙▌▙▖  ▙▌█▌▙▌▙▌▄▌

    Fontes de dados
```

---


| Fonte | Domínio | Cobertura | Autenticação |
|---|---|---|---|
| **BCB SGS** | Banco Central | Selic, CDI, IPCA, IGP-M, câmbio, PIB, desemprego — 18k+ séries temporais | — |
| **BCB Olinda PTAX** | Banco Central | USD/BRL, EUR/BRL e todas moedas rastreadas; ponto e período | — |
| **BCB Olinda Focus** | Banco Central | Boletim Focus (semanal) — anual, mensal, Selic, Top-5 | — |
| **CVM** | Regulador | Empresas registradas, demonstrações DFP/ITR, **fatos relevantes/comunicados (IPE)**, **formulário cadastral (FCA — ticker→CNPJ resolver, setor, DRI)**, catálogo + cota diária de fundos, **composição da carteira (CDA)**, **lâmina + rentabilidade mensal/anual**, **perfil de cotistas** | — |
| **IBGE Agregados v3** | Instituto de estatística | IPCA detalhado por 10 grupos + 365 subitens, INPC, PIB trimestral | — |
| **IPEA Data (OData v4)** | Instituto de pesquisa | ~8k séries macro curadas (histórico desde a década de 1940), busca no catálogo, metadados | — |
| **Tesouro Transparente** | Tesouro Nacional | Tesouro Direto — preços e taxas históricos | — |
| **B3** | Bolsa | Cotações atuais via `yfinance`, **COTAHIST oficial (1986+)** ano/mês/dia, **composição teórica de índices** (IBOV, IBrX, SMLL, IDIV, IFIX + 14 sectoriais) | — |
| **ANBIMA** | Mercado | IMA (família IRF-M, IMA-B, IMA-S, IMA-Geral) retrato do dia + **histórico via formulário Série Histórica**, ETTJ (curva zero), debêntures secundário | — |
| **Receita Federal** | Arrecadação | Arrecadação federal por ano, mês, UF e tributo | — |
| **ANEEL** | Energia | Resultados de leilões de geração e transmissão | — |
| **SUSEP** | Seguros | Entidades supervisionadas e identificadores FIP/CNPJ | — |
| **Open Finance Brasil** | Ecossistema OFB | Diretório público (`participants`, `roles`, `apiresources`, JWKS, `.well-known`) + Portal de Dados (10 datasets públicos de indicadores e rankings) | — |
| **Registro** | Multifonte | **Resolvedor CNPJ ↔ ticker ↔ nome** — SQLite FTS5 embarcado no pacote wheel (~50k entidades CVM+SUSEP+B3); uma consulta MATCH cobre exato, fragmento e aproximado | — (offline) |

> **Nota sobre ANBIMA.** Usamos os arquivos públicos em `www.anbima.com.br/informacoes/*`
> (XLS / CSV / TXT atualizados diariamente), não a API comercial Sensedia
> (que exige cadastro institucional). Os números são os mesmos canônicos
> publicados pela ANBIMA — só servidos como arquivos. Se no futuro alguém
> da comunidade tiver acesso à API autenticada e quiser contribuir com
> dados quase em tempo real, o módulo `findata.auth` segue pronto pra
> ser reutilizado — veja [docs/SOURCES_WITH_AUTH.md](docs/SOURCES_WITH_AUTH.md).

```text
▘    ▗   ▜
▌▛▌▛▘▜▘▀▌▐ ▀▌▛▘▀▌▛▌
▌▌▌▄▌▐▖█▌▐▖█▌▙▖█▌▙▌

    Instalação
```

---


Um comando único — as fontes públicas ficam prontas pra usar:

```bash
pip install findata-br
```

### O que vai ser instalado

findata-br é Python 3.11+ e depende de uma stack enxuta de bibliotecas
estáveis e bem mantidas. Nada de infra, nada de banco de dados, nada de
fila/serviço auxiliar — tudo acontece em processo único.

| Pacote | Versão | Pra que serve |
|---|---|---|
| [`fastapi`](https://fastapi.tiangolo.com/) | `>=0.115` | Servidor HTTP + geração automática da interface Swagger em `/docs` |
| [`uvicorn[standard]`](https://www.uvicorn.org/) | `>=0.34` | Laço de eventos ASGI assíncrono que serve o FastAPI (com `uvloop`, `httptools`, `watchfiles`) |
| [`httpx`](https://www.python-httpx.org/) | `>=0.28` | Cliente HTTP assíncrono usado em todas as fontes (BCB, CVM, IPEA, etc.) |
| [`pydantic`](https://docs.pydantic.dev/) | `>=2.0` | Modelos tipados e validação das respostas de API |
| [`fastapi-mcp`](https://github.com/tadata-org/fastapi_mcp) | `>=0.4` | Monta o servidor MCP em `/mcp` a partir das rotas FastAPI |
| [`typer`](https://typer.tiangolo.com/) | `>=0.15` | Estrutura da CLI `findata ...` |
| [`rich`](https://rich.readthedocs.io/) | `>=13.0` | Tabelas coloridas e banner animado no terminal |
| [`slowapi`](https://slowapi.readthedocs.io/) | `>=0.1.9` | Limitação de chamadas por IP (protege a rota pública) |
| [`yfinance`](https://github.com/ranaroussi/yfinance) | `>=0.2.50` | Cotações B3 via Yahoo Finance (puxa `pandas`/`numpy` como dependências transitivas) |

Total instalado: ~70 MB (a maior fatia é `pandas` + `numpy`, transitivas do `yfinance`).
Se sua implantação precisa ser mais enxuta e você não usa as rotas `/b3/*`, dá pra
pular o `yfinance` — veja a seção [Instalação mínima](#instalacao-minima) abaixo.

### Instalação mínima

Só quer as fontes de dados públicos sem `yfinance`/`pandas`/`numpy`? Instale
sem dependências e adicione só o que precisar:

```bash
pip install findata-br --no-deps
pip install fastapi 'uvicorn[standard]' httpx pydantic fastapi-mcp typer rich slowapi
```

Isso economiza ~40 MB mas as rotas `/b3/*` e o comando `findata b3 ...` vão
retornar `503 Serviço indisponível` até `yfinance` ser instalado.

### Desenvolvimento local

```bash
git clone https://github.com/robertoecf/findata-br.git
cd findata-br
pip install -e '.[dev]'           # núcleo + pytest, ruff, mypy, respx
bash scripts/git/install-hooks.sh # ganchos de pre-commit + pre-push
```

```text
▌▌▛▘▛▌
▙▌▄▌▙▌

    Uso
```

---


### CLI

```bash
findata bcb series              # catálogo de séries nomeadas
findata bcb get selic -n 10     # últimos 10 valores da Selic
findata bcb get ipca            # IPCA mensal
findata bcb ptax                # USD/BRL de hoje
findata bcb focus -i IPCA -n 5  # expectativas do Focus

findata tesouro search IPCA+
findata tesouro history "Tesouro IPCA+ 2035" -n 30

findata ibge ipca -n 6          # IPCA quebrado por grupo

findata ipea catalog            # séries IPEA curadas
findata ipea search desemprego  # busca textual em ~8k séries
findata ipea get BM12_TJOVER12 -n 12

findata openfinance participants --role DADOS -n 20
findata openfinance endpoints --api-family channels -n 20
findata openfinance datasets

findata cvm search Petrobras

# Fundos: holdings (CDA), lâmina, perfil de cotistas
findata cvm holdings 00.280.302/0001-60 -y 2026 -m 3
findata cvm lamina   00.280.302/0001-60 -y 2026 -m 3
findata cvm profile  00.280.302/0001-60 -y 2026 -m 3

findata b3 quote PETR4
findata b3 history VALE3 -p 1y

findata anbima ima                          # retrato do dia (todos os índices)
findata anbima ima -i IMA-B                 # filtra uma família
findata anbima ettj -d 2026-04-22           # curva zero numa data
findata anbima debentures -e Petrobras      # debêntures por emissor

# Registro: resolve CNPJ ↔ ticker ↔ nome em qualquer formato
findata registry lookup 33000167000101       # CNPJ sem máscara → Petrobras (cvm + b3)
findata registry lookup "33.000.167/0001-01" # CNPJ com máscara → mesmo resultado
findata registry lookup PETR4                # ticker B3 → Petrobras
findata registry lookup "porto seguro"       # fragmento do nome → companhia aberta + entidades SUSEP
findata registry meta                        # hash da compilação + contagens por fonte

findata serve                   # sobe o servidor HTTP + MCP
```

### Biblioteca Python

```python
import asyncio
from findata.sources.bcb import sgs, ptax, focus
from findata.sources.ipea import get_series_values
from findata.registry import lookup
from findata.sources.openfinance import get_participants, summarise_participants

async def main() -> None:
    selic = await sgs.get_series_by_name("selic", n=5)
    print(selic)

    usd = await ptax.get_ptax_usd()  # hoje
    print(usd)

    ipca_expect = await focus.get_focus_annual("IPCA", top=3)
    print(ipca_expect)

    # Selic over mensal do IPEA (série desde 1974)
    hist = await get_series_values("BM12_TJOVER12", top=12)
    print(hist)

    # Open Finance público — participantes do diretório
    participants = await get_participants()
    print(summarise_participants(participants[:3]))

    # Registro — uma chamada resolve qualquer formato de identificador
    res = await lookup("PETR4")
    if res.entities:
        e = res.entities[0]
        print(f"{e.nome} (CNPJ {e.cnpj}, fontes={e.sources}, tickers={e.tickers})")

asyncio.run(main())
```

### Registro — resolvedor CNPJ / ticker / nome

Um catálogo SQLite embarcado no wheel mapeia ~50.000 entidades brasileiras
(companhias CVM + fundos + SUSEP) com enriquecimento opcional de tickers B3.
Uma única consulta MATCH resolve:

```python
from findata.registry import lookup

# Todos esses retornam Petrobras:
await lookup("33000167000101")        # CNPJ sem máscara
await lookup("33.000.167/0001-01")    # CNPJ com máscara
await lookup("PETR4")                 # ticker B3
await lookup("9512")                  # cod_cvm
await lookup("petrobras")             # nome (aproximado)
```

O `Entity.rank` (BM25) discrimina match exato (~ -10) de match difuso (~ -2),
útil para agentes e consumidores decidirem confiança. A SQLite é reconstruída
semanalmente via CI (`.github/workflows/rebuild-registry.yml`) e atualizada
no PyPI a cada release.

### API REST

```bash
findata serve                # http://localhost:8000
curl http://localhost:8000/bcb/series/name/selic?n=5
curl 'http://localhost:8000/bcb/focus/annual?indicator=IPCA&top=3'
curl 'http://localhost:8000/registry/lookup?q=33000167000101'
curl 'http://localhost:8000/registry/lookup?q=PETR4'
curl 'http://localhost:8000/openfinance/participants?role=DADOS&limit=20'
curl http://localhost:8000/docs     # interface Swagger
curl http://localhost:8000/redoc    # documentação ReDoc
```

### Servidor MCP

A rota MCP é gerada automaticamente a partir das rotas FastAPI. Qualquer
cliente MCP (Claude Desktop, Cursor, Codex, Continue) consegue conectar em
`http://<servidor>:<porta>/mcp` e chamar todas as rotas do findata como
ferramentas.

```jsonc
// Exemplo de configuração de cliente MCP
{
  "mcpServers": {
    "findata-br": { "url": "http://localhost:8000/mcp" }
  }
}
```

### Rodando como servidor MCP público

Quer compartilhar sua instância com a comunidade? O guia
[**docs/DEPLOY_PUBLIC.md**](docs/DEPLOY_PUBLIC.md) mostra como subir o
findata-br no seu PC/WSL com **Cloudflare Tunnel** em ~20 min, custo R$ 0:
HTTPS automático, URL fixa, proteção contra DDoS e limite de chamadas embutido. Quando a
URL pública estiver no ar, qualquer pessoa pode apontar o Claude Desktop /
Cursor / Codex pra ela e usar as rotas como ferramentas MCP.

- Limite de chamadas configurável por variável de ambiente: `FINDATA_RATE_LIMIT_DEFAULT="60/minute;1000/day"`.
- `/health`, `/stats` e Swagger em `/docs` — observabilidade pronta para uso.
- `deploy/docker-compose.prod.yml` e `deploy/findata-br.service` prontos para produção.

```text
        ▘▗   ▗
▀▌▛▘▛▌▌▌▌▜▘█▌▜▘▌▌▛▘▀▌
█▌▌ ▙▌▙▌▌▐▖▙▖▐▖▙▌▌ █▌
     ▌

    Arquitetura
```

---


```
 findata/
 ├─ http_client.py        ← cliente httpx assíncrono c/ cache, retentativas, URLs OData seguras
 ├─ banner.py             ← banner animado da CLI
 ├─ cli.py                ← aplicação Typer
 ├─ api/
 │   ├─ app.py            ← FastAPI + montagem do MCP
 │   └─ routers/          ← uma rota por fonte
 └─ sources/              ← fontes externas
     ├─ bcb/   (sgs, ptax, focus)
     ├─ cvm/   (companhias, demonstrativos, fundos, parser)
     ├─ ibge/  (indicadores)
     ├─ ipea/  (séries)
     ├─ tesouro/ (títulos)
     ├─ b3/    (cotações)      ← opcional, atrás dos extras
     ├─ anbima/ (índices, ETTJ, debêntures)
     ├─ openfinance/ (diretório e portal públicos)
     └─ demais fontes regulatórias / públicas
```

Cada fonte é um adaptador assíncrono, tipado e enxuto sobre a rota pública oficial.
Todas compartilham `http_client.get_json` / `get_bytes` — assim reuso de conexões, retentativas
e cache ficam centralizados em um único lugar.

```text
▗     ▗
▜▘█▌▛▘▜▘█▌▛▘
▐▖▙▖▄▌▐▖▙▖▄▌

    Testes
```

---


```bash
pytest                       # testes unitários + API rápidos (sem rede)
pytest -m integration        # consulta as APIs públicas reais
pytest -m ""                 # roda tudo
```

Os testes de integração são pulados por padrão — dependem de acesso à rede e
do uptime dos terceiros. A suíte padrão roda testes unitários e de API sem rede; os testes de integração
ficam marcados separadamente para validação contra fontes públicas reais.

```text
       ▌
▛▘▛▌▀▌▛▌▛▛▌▀▌▛▌
▌ ▙▌█▌▙▌▌▌▌█▌▙▌
             ▌

    Roteiro — próximos passos
```

---


- **Implantação** — Dockerfile + `docker-compose` para servidor local em um comando.
- **CI/CD** — GitHub Actions em cada push; publicação no PyPI em tag.
- **Limitação de chamadas** — middleware `slowapi` (para implantações públicas).
- **Observabilidade** — logs JSON estruturados, `/metrics` (Prometheus), OpenTelemetry opcional.
- **ANBIMA** — índices IMA, IMA-B, IDkA, IHFA.
- **B3 nativo** — consumir os arquivos oficiais da B3 (índices, COTAHIST) para soltar a dependência de `yfinance`.
- **Expansão IBGE** — PNAD Contínua, produção industrial, comércio varejista, confiança.
- **Cache Redis** — opção explícita para cache distribuído em implantações com múltiplas réplicas.
- **SDK TypeScript** — cliente gerado a partir da especificação OpenAPI.

```text
           ▘ ▌   ▌
▛▘▛▌▛▛▌▌▌▛▌▌▛▌▀▌▛▌█▌
▙▖▙▌▌▌▌▙▌▌▌▌▙▌█▌▙▌▙▖

    Comunidade
```

---


findata-br é **código aberto pra durar** — MIT, sem CLA, sem adotar fornecedor
comercial como dependência central. O roteiro depende de quem usa: se você sentir falta de uma fonte
(ANBIMA, SUSEP, BNDES, ...), abra uma
[chamado usando o modelo "Nova fonte"](https://github.com/robertoecf/findata-br/issues/new?template=new-source.yml).

Qualquer desenvolvedor brasileiro interessado em dados financeiros abertos é
convidado a hospedar sua própria instância pública e colaborar com pedidos de alteração.

```text
      ▗   ▘▌   ▘   ▌
▛▘▛▌▛▌▜▘▛▘▌▛▌▌▌▌▛▌▛▌▛▌
▙▖▙▌▌▌▐▖▌ ▌▙▌▙▌▌▌▌▙▌▙▌

    Contribuindo
```

---


Guia completo em [CONTRIBUTING.md](CONTRIBUTING.md). Resumo rápido:

```bash
pip install -e '.[dev]'
bash scripts/git/install-hooks.sh   # habilita ganchos de pre-commit + pre-push
ruff check src tests                # lint (núcleo + proteções para agentes)
mypy src                            # checagem estrita de tipos
pytest                              # testes unitários + API (sem rede)
```

Mantenha as mudanças tipadas (`mypy --strict`), validadas pelo lint (`ruff check`) e
cobertas por testes. Para novas fontes, adicione testes de integração em
`tests/test_integration.py` (marcador `integration`). Para o resto, prefira
testes unitários com `respx` que não batem em rede.

```text
▜ ▘
▐ ▌▛▘█▌▛▌▛▘▀▌
▐▖▌▙▖▙▖▌▌▙▖█▌

    Licença
```

---


[MIT](LICENSE) — use como quiser.

<div align="center">
<sub>Feito para o ecossistema de dados abertos do Brasil.</sub>
</div>
