# openfindata-ship

Skill versionada **somente no repositório**. Não há install obrigatório em
`~/.agents/skills`.

Fonte canônica:

```text
docs/agents/openfindata-ship/SKILL.md
```

Agentes devem ler este path no checkout/worktree atual. Não criar cópia local
paralela como source of truth.

Helpers:

- `docs/agents/openfindata-ship/scripts/readiness.sh` — hygiene de worktree/branch antes do ship
- `docs/agents/openfindata-ship/scripts/check-pr-threads.sh` — falha se houver review threads abertas

Preflight do repo (fora desta pasta):

```bash
bash scripts/ship/preflight.sh
```
