# Dados Financeiros Abertos

Infraestrutura open source para consultar dados financeiros públicos do Brasil em
Python, REST, CLI e MCP.

[![CI](https://img.shields.io/github/actions/workflow/status/robertoecf/openfindata/ci.yml?branch=main&label=CI&logo=github)](https://github.com/robertoecf/openfindata/actions/workflows/ci.yml)
![Versão](https://img.shields.io/badge/versão-0.3.1--alpha-009c3b)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue?logo=python&logoColor=white)
[![Licença MIT](https://img.shields.io/badge/licença-MIT-yellow.svg)](LICENSE)
![Estado](https://img.shields.io/badge/status-alpha-orange)

## O que é

O projeto agrega fontes públicas brasileiras em uma camada única e auditável para
analistas, desenvolvedores, pesquisadores e agentes:

- biblioteca Python assíncrona;
- API REST com Swagger e ReDoc;
- CLI `findata`;
- servidor MCP em `/mcp`;
- registro local para resolver CNPJ, ticker e nome.

As fontes principais não exigem chaves de API e os testes unitários não acessam a
rede. O slug de distribuição é `openfindata`; o pacote importável e a
CLI continuam sendo `findata`.

## Instalação

```bash
pip install openfindata
```

Para desenvolvimento local:

```bash
git clone https://github.com/robertoecf/openfindata.git
cd openfindata
pip install -e '.[dev]'
bash scripts/git/install-hooks.sh
```

## Uso rápido

### CLI

```bash
findata bcb get selic -n 10
findata bcb ptax
findata cvm search Petrobras
findata b3 quote PETR4
findata registry lookup 33000167000101
findata serve
```

### Python

```python
import asyncio

from findata.registry import lookup
from findata.sources.bcb import sgs


async def main() -> None:
    selic = await sgs.get_series_by_name("selic", n=5)
    print(selic)

    entity = await lookup("PETR4")
    print(entity.entities[0])


asyncio.run(main())
```

### REST e MCP

```bash
findata serve
curl 'http://localhost:8000/bcb/series/name/selic?n=5'
curl 'http://localhost:8000/registry/lookup?q=PETR4'
```

- Site local: `http://localhost:8000/`
- Chart Lab: `http://localhost:8000/charts`
- Swagger: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/redoc`
- MCP: `http://localhost:8000/mcp`

O Chart Lab é a referência visual e informacional para gráficos do projeto, mas
o renderer pode ser SVG, PNG, HTML inline ou TradingView Lightweight Charts. O
contrato detalhado fica em [docs/CHART_STANDARDS.md](docs/CHART_STANDARDS.md).

## Fontes suportadas

O README mantém só o mapa de alto nível. A matriz completa de fontes, endpoints,
notas de autenticação e exemplos de consulta fica em
[docs/SOURCES_AND_ENDPOINTS.md](docs/SOURCES_AND_ENDPOINTS.md).

Fontes hoje expostas: BCB, Base dos Dados, CVM, Tesouro, IBGE, IPEA, Open
Finance Brasil, B3, Yahoo Finance experimental, ANBIMA, Receita Federal, ANEEL,
SUSEP e o registro offline CNPJ/ticker/nome.

## Documentação

- [Fontes e endpoints](docs/SOURCES_AND_ENDPOINTS.md)
- [Padrão de gráficos](docs/CHART_STANDARDS.md)
- [Deploy público](docs/DEPLOY_PUBLIC.md)
- [Open Finance público](docs/OPENFINANCE_PUBLIC.md)
- [Fontes com autenticação](docs/SOURCES_WITH_AUTH.md)
- [Prioridades de fontes](docs/SOURCE_PRIORITIES.md)
- [Manifesto](MANIFESTO.txt)
- [Contribuição](CONTRIBUTING.md)

## Qualidade

Antes de propor merge ou release, rode pelo menos:

```bash
ruff format --check src/ tests/ scripts/
ruff check src/ tests/ scripts/
mypy src/findata
pytest tests/ -q
```

Os testes de integração contra APIs públicas reais ficam separados por marcador:

```bash
pytest -m integration
```

## Escopo

Este projeto consulta dados públicos. Ele não consulta dados privados de clientes,
não armazena credenciais de usuário e não depende de fornecedores comerciais como
camada central.

## Licença

[MIT](LICENSE).
