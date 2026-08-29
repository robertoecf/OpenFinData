# Mapa de orientação do repo

Para agentes (e humanos) chegando frios: o arco do repo em ponteiros. Este
arquivo aponta, não reconta; a fonte canônica de cada item é o link.

Palavras-chave: orientação, onboarding de agente, decisões assentadas, becos
mortos, fronteira atual, openfindata, findata.

## O que é isto

- Produto e escopo: [`README.md`](../../README.md), [`MANIFESTO.txt`](../../MANIFESTO.txt).
- Convenções universais de código e gates: [`AGENTS.md`](../../AGENTS.md).
- Harness Claude (worktrees, ship): [`CLAUDE.md`](../../CLAUDE.md).
- Contribuição humana: [`CONTRIBUTING.md`](../../CONTRIBUTING.md).
- Superfície MCP curada: [`docs/MCP_SURFACE.md`](../MCP_SURFACE.md).
- Padrões de gráfico: [`docs/CHART_STANDARDS.md`](../CHART_STANDARDS.md).

## Decisões assentadas (leia antes de reabrir)

| Pergunta | Resposta vigente | Onde |
|---|---|---|
| Qual o slug de distribuição vs import/CLI? | Pacote PyPI `openfindata`; import e CLI `findata` | `AGENTS.md`, `pyproject.toml` |
| Onde vive uma fonte nova? | `src/findata/sources/<source>/` com route + CLI + testes + docs + respx juntos | `AGENTS.md`, `CONTRIBUTING.md` |
| Rede nos unit tests? | Proibido. `respx` nos unitários; live só `@pytest.mark.integration` | `AGENTS.md`, CI nightly |
| Credenciais no repo? | Nunca. Fontes públicas preferidas; BdD usa billing project do operador via env | `AGENTS.md`, `docs/SOURCES_WITH_AUTH.md` |
| MCP: 1:1 com REST ou curado? | Catálogo curado em `mcp_app` (~25 tools); REST intacto | `docs/MCP_SURFACE.md` |
| MCP público vs interno? | Worker `openfindata.com.br/mcp` (macro JSON + `cvm_fund`); FastAPI/Tailscale tem o catálogo completo | `docs/DEPLOY_WORKERS_MCP.md` |
| Code mode no MCP? | Opt-in via `FINDATA_MCP_CODE_MODE=1`; off por default | `docs/MCP_SURFACE.md`, `mcp_app.py` |
| Charts: quais deps de plot? | Não adicionar matplotlib/pandas/plotly etc. só para gráfico | `AGENTS.md`, `docs/CHART_STANDARDS.md` |
| Publicar no PyPI? | Só com aprovação humana explícita | `AGENTS.md` |
| Onde agentes implementam? | Worktree dedicada; root/`main` são inspect-only | `CLAUDE.md`, `docs/agents/openfindata-ship/` |

## O que morreu e por quê

- CI “pendente” em `.github-pending/`: obsoleto. Workflows vivem em
  `.github/workflows/` (`ci.yml`, `integration.yml`, `rebuild-registry.yml`).
- Auto-MCP 1:1 com todas as rotas REST: substituído pela superfície curada.
- Nome legado do repo `findata-br` / import antigo: CLI e import permanecem
  `findata` por compatibilidade; distribuição é `openfindata`.

## Você está aqui (fronteira)

- Workflows de qualidade de agente: este diretório `docs/agents/`.
- Ship parent: [`openfindata-ship/SKILL.md`](openfindata-ship/SKILL.md).
- Gate de confiança MCP/IA: [`mcp-trust-review.md`](mcp-trust-review.md).
- Gates locais: [`quality.md`](quality.md) e `bash scripts/ship/preflight.sh`.
- Backlog de fontes: [`docs/SOURCE_PRIORITIES.md`](../SOURCE_PRIORITIES.md).
- Deploy público: [`docs/DEPLOY_PUBLIC.md`](../DEPLOY_PUBLIC.md).

## Regra de atualização

Quando uma decisão assentada mudar de forma durável, atualize a linha
correspondente aqui e o arquivo canônico apontado. Entradas são uma linha e um
link; o conteúdo vive na fonte canônica.
