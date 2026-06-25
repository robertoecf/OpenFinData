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

# Instala os git hooks (opcional mas recomendado)
bash scripts/git/install-hooks.sh
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

Instalados via `bash scripts/git/install-hooks.sh`, que aponta
`core.hooksPath` para `.githooks/`. Dois hooks:

- **pre-commit** — só no diff staged, em segundos:
  - `ruff check` + `ruff format --check` nos arquivos `.py` staged.
  - `ggshield secret scan pre-commit` (se `ggshield` estiver instalado).
- **pre-push** — rede de segurança completa:
  - `ruff format --check` + `ruff check` no repo inteiro (`src`, `tests`, `scripts`).
  - `mypy --strict` em `src/findata`.
  - `pytest -q` (unit + API; integration fica só na CI).

Pra desinstalar: `git config --unset core.hooksPath`.

## Testes

```bash
pytest                       # padrão — unit + API (sem rede)
pytest -m integration        # bate nos endpoints públicos reais
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
