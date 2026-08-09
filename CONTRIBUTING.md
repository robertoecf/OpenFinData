# Contribuindo para o Dados Financeiros Abertos

> PRs são bem-vindos. Este guia explica como configurar o ambiente local e
> quais guardrails de formatação, lint, tipos e testes o projeto usa.

## Setup em 30 segundos

```bash
git clone https://github.com/robertoecf/openfindata.git
cd openfindata
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'

# Root checkout é inspect-only. Crie uma worktree antes de commit/push:
git worktree add .worktrees/minha-feature -b feature/minha-feature
cd .worktrees/minha-feature

# Instala os git hooks (recomendado; compartilhados por todas as worktrees)
bash scripts/git/install-hooks.sh
```

## Worktrees (obrigatório)

Root checkout e `main` são **inspect-only** — os hooks bloqueiam commit/push
neles. Trabalhe numa worktree:

| Quem | Branch | Worktree |
|---|---|---|
| Humano | `feature/<slug>`, `fix/<slug>`, … | `.worktrees/<slug>` (ou path sob `.worktrees/`) |
| Claude / Cursor | `claude/<slug>` ou `cursor/<slug>` | `.claude/worktrees/*` ou `$HOME/.cursor/worktrees/*` |
| Codex | `codex/<slug>` | `.worktrees/codex-*` |

Ver [`CLAUDE.md`](CLAUDE.md) e [`docs/agents/openfindata-ship/`](docs/agents/openfindata-ship/).

Gate local canônico antes de publicar:

```bash
bash scripts/ship/preflight.sh
```

## Os três tools da casa

A filosofia separa responsabilidades entre formatação, lint, tipos e testes:

| Papel | Ferramenta neste projeto | Responsabilidade |
|---|---|---|
| Formatter + lint base | **Ruff** (`ruff format` + `ruff check`) | Formatação e higiene de código |
| Guardrails de IA | **Ruff Pylint rules** (`PLR*`, `C901`) | Limites de complexidade, parâmetros e magic numbers |
| Type checking | **Mypy** (`--strict`) | Tipos estritos |
| Testes | **Pytest** (`-m "not integration"` por padrão) | Testes unitários e de API sem rede |
| Secret scan | **ggshield** (opcional, no pre-commit) | Detecção local de segredos |

## Guardrails de IA (Pylint Refactor rules)

O `pyproject.toml` concentra as guardrails de IA via Ruff:

| Guardrail | Regra Ruff | Limite |
|---|---|---|
| Tamanho de função | `PLR0915` statements | 50 statements |
| Parâmetros | `PLR0913` | 6 (FastAPI handlers precisam) |
| Magic numbers | `PLR2004` | Constantes nomeadas obrigatórias |
| (complexidade) | `C901` (McCabe) | 10 |
| (branches) | `PLR0912` | 12 |
| (returns) | `PLR0911` | 6 |
| Print acidental | `T201` | `print()` proibido fora de `banner.py` |
| Segurança básica | `S` (flake8-bandit) | Ativo |

Exceções conscientes:

- Routers FastAPI ignoram `B008` (o idiom `Query(default=...)` dispara falso-positivo).
- `cli.py` ignora `PLR0913` (comandos Typer somam muitos `--flag`).
- Testes ignoram `S` (bandit) + `PLR2004` (magic numbers em asserts) + `ERA`.

## Fluxo de trabalho

```bash
# Antes de commitar
ruff format src tests scripts    # auto-format
ruff check src tests scripts --fix # auto-fix o que dá
mypy src/findata                 # type check
pytest                           # unit + API (rápido, ~1s)

# Ou deixe os hooks fazerem: git commit dispara o pre-commit; git push dispara o pre-push.
```

## Git hooks

Instalados via `bash scripts/git/install-hooks.sh`, que copia os hooks para
`<git-common-dir>/openfindata-hooks/` (compartilhado por todas as worktrees) e
aponta `core.hooksPath` para lá. Três hooks:

- **pre-commit** — contexto (worktree/branch) + lint no staged:
  - bloqueia commit no root checkout ou em `main` (use worktree; ver acima);
  - `ruff check` + `ruff format --check` nos arquivos `.py` staged;
  - `ggshield secret scan pre-commit` (se `ggshield` estiver instalado).
- **pre-push** — contexto + rede de segurança completa:
  - `ruff format --check` + `ruff check` no repo inteiro (`src`, `tests`, `scripts`);
  - `mypy --strict` em `src/findata`;
  - `pytest -q` (unit + API; integration fica no workflow noturno/agendado).
- **post-checkout** — aviso se o root checkout sair de `main`.

Bypass de emergência (não é fluxo normal): `OPENFINDATA_GUARDRAILS_BYPASS=1`.
Se você instalou hooks e ainda está no clone raiz, o bloqueio é esperado —
mova o trabalho para uma worktree em vez de bypassar.

Pra desinstalar: `git config --unset core.hooksPath`.

Workflows de agente (ship, MCP trust, orientation): [`docs/agents/`](docs/agents/).

## Testes

```bash
pytest                       # padrão — unit + API (sem rede)
pytest -m integration        # manual; também roda no workflow noturno/agendado
pytest -m ""                 # tudo
```

Adicione testes de integração só para **novas fontes** — para o resto,
use `respx` pra mockar httpx e manter os testes sem dependência de rede.

## Convenções de arquitetura

Alinhado ao que funciona em projetos similares (inclusive lições de
[gprossignoli/findata](https://github.com/gprossignoli/findata) —
veja `ROADMAP.md` para detalhes):

- **Um pacote por fonte** em `src/findata/sources/<fonte>/`. Não misture
  BCB com CVM num arquivo só.
- **Adapter por dependência externa.** Se precisar de um cliente novo (ex.:
  ANBIMA), crie `sources/anbima/client.py` + `models.py` + `sources/anbima/__init__.py`
  re-exportando a superfície pública. Evite três camadas cerimoniais
  (`domain/application/infrastructure/`) — nosso escopo é wrapper stateless.
- **Router por fonte** em `src/findata/api/routers/`. Um arquivo ↔ um prefixo.
- **CLI subcommand por fonte** — já exemplificado em `cli.py`.

## Commits

Um-linha imperativo, começando em lowercase, com prefixo `tipo:`:

```
feat: adicionar fonte ANBIMA com IMA-B e IDkA
fix: tratar VL_PATRIM_LIQ vazio em CVM funds daily
docs: traduzir README para pt-BR
ci: forçar Node 24 em GitHub Actions
```

Co-autoria com agentes é bem-vinda:

```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```
