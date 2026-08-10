# openfindata: Claude Code / Cursor harness

> Convenções universais de código vivem em [`AGENTS.md`](AGENTS.md). Este arquivo
> cobre só o que é específico do harness: worktrees, ship skill, gotchas.
> Não duplique convenções de código aqui.

> **Source of truth for:** harness, worktree policy, ship routing.
> **Companion:** [`AGENTS.md`](AGENTS.md), [`docs/agents/`](docs/agents/).

## Fonte de verdade

| O que | Onde |
|---|---|
| Convenções de código (universal) | [`AGENTS.md`](AGENTS.md) |
| Agent skills / workflows | [`AGENTS.md`](AGENTS.md) → [`docs/agents/`](docs/agents/) |
| Gates locais | [`docs/agents/quality.md`](docs/agents/quality.md) |
| MCP trust | [`docs/agents/mcp-trust-review.md`](docs/agents/mcp-trust-review.md) |
| Contribuição humana | [`CONTRIBUTING.md`](CONTRIBUTING.md) |

## Ship / PR

Use a skill **`openfindata-ship`** como primeira ação sempre que o request for
publicar código: commit, push, abrir/atualizar PR, ready-for-review, ou
endereçar comentários cujo resultado mude código.

Fonte canônica (somente no repo):

```text
docs/agents/openfindata-ship/SKILL.md
```

Inspeção read-only de PR pode usar `gh` direto. No momento em que edição,
push ou criação de PR entram em cena, volte para `openfindata-ship`.

PyPI e tags de release exigem aprovação humana explícita — ship nunca publica
pacote sozinho.

## Worktree Policy

### Branch naming

- Claude / Cursor: `claude/<feature-slug>` ou `cursor/<feature-slug>`
- Codex: `codex/<feature-slug>`
- Slug descreve a feature (ex.: `agent-quality-workflows`), não categoria genérica

### Estrutura

- `.claude/worktrees/*`: worktrees do Claude Code
- `$HOME/.cursor/worktrees/*`: worktrees do Cursor
- `.worktrees/codex-*`: worktrees do Codex
- **Root checkout = inspeção apenas.** Nunca implementar, commitar ou fazer push do root.
- **`main` = integração;** nunca mutar código diretamente nela.

Depois de pull/merge que altere `.githooks/*` ou `scripts/git/guardrails.sh`,
rode `bash scripts/git/install-hooks.sh` antes de confiar nos hooks locais.

### Bypass (emergência)

Só com intenção explícita do operador:

```bash
OPENFINDATA_GUARDRAILS_BYPASS=1 git commit ...
```

Não use bypass como atalho de rotina.

## Comandos úteis

```bash
bash scripts/git/install-hooks.sh
bash scripts/ship/preflight.sh
bash docs/agents/openfindata-ship/scripts/readiness.sh
.venv/bin/findata serve --reload   # ou scripts/dev_server.sh
```

### Python / `.venv` (contrato único)

Resolver usado por `scripts/ship/preflight.sh` e `scripts/git/guardrails.sh`:

1. `<worktree>/.venv/bin/python` se existir;
2. senão `<repo-root>/.venv/bin/python` (venv criado no clone raiz);
3. senão `python3` no `PATH`.

Comandos documentados como `.venv/bin/...` significam “o interpretador desse
resolver”, não “somente um `.venv` local à worktree”. Preferência: criar o
venv no root uma vez (`CONTRIBUTING.md`) e reutilizá-lo nas worktrees.

## Skills no repo

| Skill | Path |
|---|---|
| Ship | `docs/agents/openfindata-ship/SKILL.md` |
| MCP trust reviewer | `.claude/skills/mcp-trust-reviewer/SKILL.md` |

Skills de harness global (adversarial-review, deslop, handoff, tdd, …) não são
duplicadas neste repo.
