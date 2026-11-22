# AGENTS.md: Dados Financeiros Abertos

This file is for coding agents working in this repository. Keep it practical:
follow the project conventions, avoid speculative dependencies, and produce
reproducible data work.

Harness specifics (worktrees, ship routing, `.venv` resolver) are in
[Harness: ship, worktrees, commands](#harness-ship-worktrees-commands).

## Agent skills

Workflow docs live under `docs/agents/`. Keep this section as pointers:

- Cold-start orientation map: [`docs/agents/orientation.md`](docs/agents/orientation.md)
- Domain docs consumption: [`docs/agents/domain.md`](docs/agents/domain.md)
- Quality gates and preflight: [`docs/agents/quality.md`](docs/agents/quality.md)
- MCP Trust review gate: [`docs/agents/mcp-trust-review.md`](docs/agents/mcp-trust-review.md)
- MCP Trust reviewer skill: [`.claude/skills/mcp-trust-reviewer/SKILL.md`](.claude/skills/mcp-trust-reviewer/SKILL.md)
- Ship parent workflow: [`docs/agents/openfindata-ship/SKILL.md`](docs/agents/openfindata-ship/SKILL.md)

Harness-global skills (adversarial-review, deslop, handoff, tdd) live in the
host, not in this repo.

## Project baseline

- Implementation checkout: a dedicated **worktree**, never the root checkout
  and never `main`. Root/`main` are inspect-only (see [Worktree Policy](#worktree-policy)).
- Project name: Dados Financeiros Abertos.
- Distribution/package slug: `openfindata`.
- Import package and CLI remain `findata` for compatibility.
- Scope: Python library + REST API + MCP server + CLI for Brazilian public
  financial data.
- Prefer public, reproducible sources. Do not introduce API keys, tokens, or
  private credentials into code, tests, docs, examples, or generated artifacts.
- Do not commit generated caches, local virtualenvs, temporary chart outputs, or
  binary artifacts other than the generated registry SQLite already owned by the
  project.

## Quality gates

Before a code change is considered ready, run the smallest relevant check first,
then the full gate from the **worktree** before merging or release work:

```bash
bash scripts/ship/preflight.sh
```

Expanded commands, preflight modes and the docs-only check:
[`docs/agents/quality.md`](docs/agents/quality.md).

## Source integration pattern

- New source modules live under `src/findata/sources/<source>/`.
- Add route, CLI, tests, docs, and mocked HTTP coverage together when exposing a
  new public dataset.
- Use `findata.http_client.get_json` / `get_bytes` for network access.
- Unit tests should not hit live APIs. Use `respx`; mark live checks as
  `@pytest.mark.integration`.
- Keep `mypy --strict` clean for new code.

## Base dos Dados / BigQuery

BigQuery bills by bytes processed: start with tiny `LIMIT` queries. Before any
Base dos Dados task, read
[`docs/source-notes/basedosdados.md`](docs/source-notes/basedosdados.md)
(billing project, env vars, credential and evidence rules).

## Charts

Chart requests: follow [`docs/CHART_STANDARDS.md`](docs/CHART_STANDARDS.md)
before generating anything (minimum information contract, color tokens,
renderer policy, no plotting libraries as project dependencies).

## Release guardrails

- Do not publish to PyPI without explicit human approval.
- Do not tag a release until tests and adversarial review are clean, and never without explicit human approval.

## Harness: ship, worktrees, commands

### Ship / PR

Use a skill **`openfindata-ship`** como primeira ação sempre que o request for
publicar código: commit, push, abrir/atualizar PR, ready-for-review, ou
endereçar comentários cujo resultado mude código.

Fonte canônica (somente no repo):

```text
docs/agents/openfindata-ship/SKILL.md
```

Inspeção read-only de PR pode usar `gh` direto. No momento em que edição,
push ou criação de PR entram em cena, volte para `openfindata-ship`.

### Worktree Policy

#### Branch naming

- Claude / Cursor: `claude/<feature-slug>` ou `cursor/<feature-slug>`
- Codex: `codex/<feature-slug>`
- Slug descreve a feature (ex.: `agent-quality-workflows`), não categoria genérica

#### Estrutura

- `.claude/worktrees/*`: worktrees do Claude Code
- `$HOME/.cursor/worktrees/*`: worktrees do Cursor
- `.worktrees/codex-*`: worktrees do Codex
- **Root checkout = inspeção apenas.** Nunca implementar, commitar ou fazer push do root.
- **`main` = integração;** nunca mutar código diretamente nela.

Depois de pull/merge que altere `.githooks/*` ou `scripts/git/guardrails.sh`,
rode `bash scripts/git/install-hooks.sh` antes de confiar nos hooks locais.

#### Bypass (emergência)

Só com intenção explícita do operador:

```bash
OPENFINDATA_GUARDRAILS_BYPASS=1 git commit ...
```

Não use bypass como atalho de rotina.

### Comandos úteis

```bash
bash docs/agents/openfindata-ship/scripts/readiness.sh
.venv/bin/findata serve --reload   # ou scripts/dev_server.sh
```

#### Python / `.venv` (contrato único)

Resolver usado por `scripts/ship/preflight.sh` e `scripts/git/guardrails.sh`:

1. `<worktree>/.venv/bin/python` se existir;
2. senão `<repo-root>/.venv/bin/python` (venv criado no clone raiz);
3. senão `python3` no `PATH`.

Comandos documentados como `.venv/bin/...` significam “o interpretador desse
resolver”, não “somente um `.venv` local à worktree”. Preferência: criar o
venv no root uma vez (`CONTRIBUTING.md`) e reutilizá-lo nas worktrees.
