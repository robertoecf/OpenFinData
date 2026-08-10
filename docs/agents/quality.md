# Quality gates

Fonte canônica dos comandos de qualidade locais e de como eles se relacionam
com hooks, ship e CI.

## Gate completo (merge / release / ship)

A partir da raiz da **worktree** (não do root checkout):

```bash
bash scripts/ship/preflight.sh
```

Equivalente expandido (mesmo conjunto que o preflight `--push`). Interpretador:
worktree `.venv`, senão `.venv` na raiz do repo comum, senão `python3` — ver
`CLAUDE.md` § Python / `.venv`.

```bash
# Prefer: bash scripts/ship/preflight.sh
"$PY" -m ruff format --check src/ tests/ scripts/
"$PY" -m ruff check src/ tests/ scripts/
"$PY" -m mypy src/findata
"$PY" -m pytest tests/ -q
```

Docs-only: no mínimo `git diff --check`.

## Modos do preflight

| Modo | Uso |
|---|---|
| `bash scripts/ship/preflight.sh` / `--push` | Readiness + gate completo; escreve evidência |
| `--quick` | Só ruff check + format --check (iteração rápida) |
| `--ci` | Gate completo sem readiness (paridade com `ci.yml` unitária) |
| `--skip-readiness` | Útil em runners/CI; não use no ship local normal |

Evidência: `<git-common-dir>/openfindata-verify/preflight.ok` amarrada ao SHA
do `HEAD`.

## Camadas

| Camada | O que roda |
|---|---|
| pre-commit (hook) | Contexto worktree/branch + ruff no staged + ggshield opcional |
| pre-push (hook) | Contexto + gate completo (ruff/mypy/pytest sem integration) |
| ship skill | Deslop + adversarial review + MCP trust se aplicável + preflight + PR |
| CI `ci.yml` | Matrix 3.11–3.13; coverage gate no 3.12 |
| CI `integration.yml` | Nightly / manual: `pytest -m integration` |

## Ownership das ferramentas

| Papel | Ferramenta |
|---|---|
| Formatter + lint + AI complexity | Ruff (`pyproject.toml`) |
| Types | mypy `--strict` |
| Unit/API | pytest (`-m "not integration"` default) |
| Secrets locais | ggshield (opt-in no pre-commit) |

Detalhe humano: [`CONTRIBUTING.md`](../../CONTRIBUTING.md).
Adversarial review: skill de harness `adversarial-review` (não duplicar aqui).
MCP/IA: [`mcp-trust-review.md`](mcp-trust-review.md).
