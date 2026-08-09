# Domain Docs

Como skills e agentes devem consumir a documentação de domínio do openfindata
antes de explorar ou alterar o código.

## Antes de explorar, leia estes

- **[`AGENTS.md`](../../AGENTS.md)** — baseline, gates, integração de fontes, BdD, charts.
- **[`docs/SOURCES_AND_ENDPOINTS.md`](../SOURCES_AND_ENDPOINTS.md)** — catálogo de endpoints.
- **[`docs/SOURCE_PRIORITIES.md`](../SOURCE_PRIORITIES.md)** — backlog e prioridade de fontes.
- **[`docs/SOURCES_WITH_AUTH.md`](../SOURCES_WITH_AUTH.md)** — política de fontes com auth.
- **[`docs/MCP_SURFACE.md`](../MCP_SURFACE.md)** — catálogo MCP curado e code mode.
- **[`docs/RESOLVER.md`](../RESOLVER.md)** — registry/resolver para lookups de agente.
- **[`docs/CHART_STANDARDS.md`](../CHART_STANDARDS.md)** — contrato informacional de gráficos.
- **`docs/source-notes/`** — notas por fonte (`basedosdados`, `yahoo`, `advfn`, …).
- **[`CLAUDE.md`](../../CLAUDE.md)** — worktrees e roteamento de ship (Claude/Cursor).

Se um arquivo não existir na worktree, siga em silêncio e use a fonte canônica
mais próxima. Não invente glossário paralelo.

## Layout

```text
/
├── AGENTS.md
├── CLAUDE.md
├── CONTRIBUTING.md
├── src/findata/
│   ├── sources/<source>/
│   ├── api/routers/
│   ├── api/mcp_app.py
│   └── web/          # Chart Lab
└── docs/
    ├── agents/       # workflows de agente (este diretório)
    ├── source-notes/
    └── *.md          # superfície, MCP, charts, deploy
```

## Vocabulário operacional

Use estes termos de forma estável em issues, PRs, testes e handoffs:

| Termo | Significado |
|---|---|
| `source` | Pacote sob `src/findata/sources/<source>/` |
| `router` | FastAPI router por fonte em `api/routers/` |
| `registry` | Índice SQLite gerado (`scripts/build_registry.py`) |
| `resolver` | Lookup CNPJ/ticker/código → entidades |
| `MCP surface` | Catálogo curado em `mcp_app`, não o REST 1:1 |
| `code mode` | Tool `findata_run_code` opt-in |
| `integration test` | Teste marcado `@pytest.mark.integration` (rede viva) |
| `Chart Lab` | UI/referência em `/charts` |

## Conflitos e gaps

Se a mudança contradisser `AGENTS.md`, `MCP_SURFACE.md` ou
`SOURCES_WITH_AUTH.md`, declare o conflito explicitamente no PR em vez de
sobrescrever em silêncio. Gap de glossário: anote no PR; não crie segundo índice.
