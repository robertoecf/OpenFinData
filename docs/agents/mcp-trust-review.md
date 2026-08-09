# MCP Trust Review: checklist canônico

> **Source of truth for:** gate de review de qualquer PR que altere a superfície
> MCP, code mode, tool catalog, ou comportamento de agente sobre dados públicos.
> **Não substitui:** auth de operadores (BdD/BigQuery), ausência de credenciais
> no repo, testes com `respx`, nem aprovação humana para PyPI.
> **Contrato de produto MCP:** [`docs/MCP_SURFACE.md`](../MCP_SURFACE.md).

## Fase atual

O gate **é review**, não CI mecânico de registry:

1. Este checklist.
2. Skill read-only `.claude/skills/mcp-trust-reviewer` em PRs com superfície MCP/IA.
3. Resultado anexado ao PR (comentário ou corpo) antes do merge.
4. Controles já existentes (code mode off por default, HTTP via `http_client`,
   sem secrets no tree) continuam obrigatórios em código.

## Quando rodar

Na dúvida, rode.

| Gatilho | Exemplos |
|---|---|
| Catálogo ou tools MCP | `src/findata/api/mcp_app.py`, descriptions, `operation_id` |
| Code mode | `findata_run_code`, `FINDATA_MCP_CODE_MODE`, sandbox/child process |
| Wiring MCP | `FastApiMCP`, mount `/mcp`, app de catálogo vs app pública |
| Docs de superfície agente | `docs/MCP_SURFACE.md`, notas que mudam contrato de tools |
| Resolver/registry usado por agentes | `RESOLVER.md`, build/validate registry tocado por tools |
| Expansão de dados sensíveis via agente | novas tools que tocam fontes com auth (`SOURCES_WITH_AUTH.md`) |

PRs sem superfície MCP/agente: `NOT_APPLICABLE` (uma linha basta).

## Papéis

| Papel | Responsabilidade |
|---|---|
| Autor do PR | Classifica a mudança, aponta evidências no diff |
| `mcp-trust-reviewer` | Review read-only; emite PASS / PASS_WITH_FOLLOW_UPS / BLOCK |
| Humano / arquiteto | Adjudica achados e decide merge |

## Classificação do PR

| Classe | Significado |
|---|---|
| `MCP_TOOL` | Nova tool ou mudança material de tool existente |
| `MCP_CODE_MODE` | Altera code mode, sandbox, ou defaults de execução |
| `MCP_SURFACE` | Curation/catalog/docs/wiring sem nova capacidade de execução |
| `AGENT_DATA` | Muda o que agentes podem buscar (auth sources, BdD, PII-adjacent) |
| `NOT_APPLICABLE` | Diff sem superfície MCP/agente |

## Eixos de verificação

### A. Curation e escopo

- [ ] Novas capacidades entram como tools curadas (ou selectors), não como flood 1:1 do REST.
- [ ] `summary`/docstring orientados a agente; `operation_id` estável.
- [ ] `docs/MCP_SURFACE.md` atualizado quando o catálogo muda.
- [ ] Não reintroduz catálogo auto-gerado a partir do app REST completo.

### B. Code mode e execução

- [ ] Code mode permanece **off por default**; enable só via env explícita.
- [ ] Child/sandbox não herda secrets indevidos; timeout/limites preservados ou justificados.
- [ ] Não há caminho novo de execução arbitrária fora do gate de code mode.
- [ ] Erros de execução não vazam paths locais sensíveis ou credenciais.

### C. Credenciais e fontes

- [ ] Nenhuma API key, refresh token, service-account JSON ou path privado no diff.
- [ ] Fontes com auth respeitam `docs/SOURCES_WITH_AUTH.md`.
- [ ] BdD/BigQuery: só project id via env; queries de exemplo com `LIMIT` pequeno.
- [ ] Evidência de PR não imprime credential paths.

### D. Rede, testes e reprodutibilidade

- [ ] Unit tests mockam HTTP (`respx`); live só `integration`.
- [ ] Uso de `findata.http_client` (ou justificativa explícita para exceção).
- [ ] Mudança de tool tem cobertura de teste ou evidência equivalente.

### E. Over-engineering (obrigatório)

Com comportamento e segurança fixos: a mesma capacidade caberia estendendo uma
tool consolidada em vez de nova tool? Há abstração especulativa? Se apagar a
layer, a complexidade some?

## Severidade

| Severidade | Uso |
|---|---|
| Blocker | Code mode on por default; secret no tree; execução arbitrária ungated; regressão que reidrata catálogo 1:1 sem curadoria |
| High | Nova tool sem doc/teste; fonte auth sem política; vazamento de path/credencial em erro |
| Medium | Doc drift do catálogo; summary fraco; cobertura parcial |
| Low | Naming/doc menor |

## Formato de saída

```markdown
## MCP Trust Review

- **Classificação:** MCP_TOOL | MCP_CODE_MODE | MCP_SURFACE | AGENT_DATA | NOT_APPLICABLE
- **Base:** <ref>
- **Head:** <sha>
- **Tools tocadas:** <lista ou n/a>
- **Conclusão:** PASS | PASS_WITH_FOLLOW_UPS | BLOCK

### Achados
| ID | Severidade | Evidência | Cenário de falha | Regra | Correção mínima |
|---|---|---|---|---|---|
| MT-1 | … | `path:line` | … | eixo | … |

Se nenhum: `NO_FINDINGS`.

### Over-engineering
<parágrafo curto ou NO_FINDINGS>
```

## Integração com ship

PRs com superfície MCP/agente precisam deste review anexado antes do merge.
Ver [`openfindata-ship/SKILL.md`](openfindata-ship/SKILL.md). Sem superfície:
registrar `NOT_APPLICABLE` uma vez e seguir.
