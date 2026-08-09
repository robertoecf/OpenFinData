---
name: openfindata-ship
description: 'Use when working in the openfindata repo and the user says "ship", "shipar", "vamos shipar", "merge", "pode mergear", "auto-merge", "automerge", asks to prepare/push/open/update a PR, asks to address PR comments with code changes, says a PR was merged and expects cleanup, or asks for deterministic pre-ship review.'
---

# Ship do openfindata

Skill versionada em `docs/agents/openfindata-ship/`. Sem install externo: o
checkout/worktree é a runtime copy.

O roteamento para esta skill nunca concede por si só permissão de merge ou
publicação PyPI. A autorização vem só dos gates explícitos abaixo.

## Autoridade de roteamento

Parent workflow para qualquer ação que possa publicar código:

- commit, push, abrir/atualizar PR, marcar ready-for-review;
- abordar comentários quando o resultado puder incluir mudanças de código ou push;
- qualquer workflow GitHub além de inspeção read-only.

Inspeção read-only de PR pode usar `gh` direto. Assim que edições, push ou
criação de PR entrarem no escopo, volte a esta skill.

## Checkpoint imediato de review

Presuma adversarial review obrigatório, salvo dispensa explícita na mensagem atual.

Antes de publicar ou fazer push material:

1. **Commit primeiro o que será publicado**, deixe a working tree limpa, depois
   revise o diff cumulativo `git diff --merge-base origin/main HEAD`. Não declare
   review completo sobre um `HEAD` que ainda não contém as mudanças a publicar.
   Se ainda houver unstaged/untracked no escopo do PR, incorpore ou exclua antes
   do review final (`readiness.sh` falha com working tree suja).
2. Review adversarial externo é tentativa obrigatória via skill/harness
   `adversarial-review` (ou Task `adversarial-reviewer` no Cursor). Percorra até
   obter review de família de modelo diferente da do autor do diff, ou registre
   degradê:
   - `CROSS_FAMILY` — família do reviewer comprovadamente diferente; nomeie ambas.
   - `EXTERNAL_SAME_FAMILY` — externo rodou mas mesma família do autor.
   - `DEGRADED_LOCAL_ONLY` — sem reviewer externo utilizável; inclua o review local.
3. Achado externo só conta com evidência `arquivo:linha` + cenário. O arquiteto
   do main loop tria o que é bloqueante.
4. Gate **MCP Trust** quando o diff tocar MCP/code mode/superfície de agente:
   leia [`../mcp-trust-review.md`](../mcp-trust-review.md) e rode a skill
   `.claude/skills/mcp-trust-reviewer`. Anexe o resultado ao PR. Sem superfície:
   `NOT_APPLICABLE` uma vez.
5. Antes do push: `bash scripts/ship/preflight.sh` (evidência amarrada ao HEAD).

## Lista de verificação adversarial (local)

Inspecione o diff cumulativo e procure:

- mudanças fora da tarefa / refactors amplos;
- marcadores de conflito; caches (`.venv`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`);
- artefatos de chart one-off (CSV/PNG/SVG/HTML temporários) sem pedido explícito;
- `print()` de debug fora dos pontos permitidos; secrets; credential paths;
- unit test batendo rede viva; nova fonte sem route+CLI+tests+docs+respx;
- catálogo MCP inchando sem curadoria; code mode default-on;
- invariantes: sem credenciais no tree; fontes públicas preferidas; mypy strict.

Corrija achados bloqueantes antes de commit/push. Achado intencional: explique.

## Significado de "ship"

1. revisar arsenal/skills relevantes;
2. gate deslop no diff (skill `deslop` do harness se disponível);
3. commit do escopo do PR; working tree limpa;
4. adversarial review do diff cumulativo commitado (+ MCP trust se aplicável);
5. corrigir achados (novo commit se preciso; re-revisar o cumulativo);
6. validar com preflight no HEAD atual;
7. push/abrir ou atualizar PR ready-for-review **só se o usuário pediu publicar**;
8. acompanhar checks/bots no head SHA e abordar comentários acionáveis;
9. parar antes do merge, salvo autorização explícita de merge/auto-merge;
10. nunca publicar PyPI nem criar tag de release sem aprovação humana explícita.

Não escreva `SHIP_REPORT.md`. Reporte evidência na conversa e no corpo do PR.

## Primeiros comandos

```bash
git rev-parse --show-toplevel
git worktree list
git status -sb
git log --oneline -5
bash docs/agents/openfindata-ship/scripts/readiness.sh
bash scripts/ship/preflight.sh
```

## Regras de worktree e branch

- Operações git mutantes (stage, commit, push, branch, worktree) só no MAIN LOOP.
  Workers não rodam git mutante.
- Root checkout = inspeção apenas. Implementação em worktree dedicada.
- `main` = integração; nunca mutar código nela.
- Branches de agente: `claude/<slug>`, `codex/<slug>`, `cursor/<slug>`.
- Worktrees Claude: `.claude/worktrees/*`. Codex: `.worktrees/codex-*`.
  Cursor: `$HOME/.cursor/worktrees/*`.
- Novas branches a partir de `origin/main`.
- Depois de pull que altere `.githooks/*` ou `scripts/git/guardrails.sh`, rode
  `bash scripts/git/install-hooks.sh`.

## Autorização de merge e auto-merge

`merge` / `pode mergear` (após parada no merge gate) autoriza fechar **um** PR:

1. atualizar estado e head SHA;
2. checks obrigatórios/ativos verdes no head;
3. threads acionáveis limpas;
4. merge só se gates passarem;
5. cleanup da branch/worktree desse PR.

`auto-merge` / `automerge` = autorização antecipada condicionada ao mesmo limpo,
fixada a um único PR. Expira ao mudar de PR/tarefa. Nunca autoriza PyPI.

## Gate deslop

Antes do adversarial final e da publicação, passe deslop no diff cumulativo
(preservar comportamento): comentários mortos, try/except defensivos anormais,
`Any` cosmético, nesting desnecessário, wrappers pass-through. Reporte reduções
ou `no removable slop found`.

## Protocolo de publicação

Somente após review + validação:

1. `git status -sb`
2. stage intencional
3. commit focado (estilo `tipo:` do `CONTRIBUTING.md`)
4. `bash scripts/ship/preflight.sh` se o HEAD mudou
5. push da branch de PR
6. abrir/atualizar PR ready-for-review (draft só se pedido explícito)
7. corpo: resumo, validação, MCP trust label se aplicável
8. loop de bots/comentários no head SHA
9. parar antes do merge salvo autorização explícita

### Loop de comentários (resumo)

```bash
gh pr view --json number,url,isDraft,headRefOid,statusCheckRollup,reviewDecision
bash docs/agents/openfindata-ship/scripts/check-pr-threads.sh <PR>
```

Aborde comentários acionáveis com mudanças cirúrgicas, re-valide, push, repita.
Responda threads e resolva as abordadas. Finalize só com threads limpas ou
itens explicitamente não acionáveis citados no relatório.

## Pós-merge

Com gatilho `merged` / `já mergeou` (ou continuidade após merge autorizado):
limpar só a branch e worktree desse PR. Não deletar trabalho não relacionado.
PyPI/tag continuam exigindo pedido humano separado.
