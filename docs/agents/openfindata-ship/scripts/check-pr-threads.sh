#!/usr/bin/env bash
# Ship-gate final scan: report unresolved review threads on a PR.
# Usage: check-pr-threads.sh <pr-number> [owner/repo]
# Exit 0 when every review thread is resolved; exit 1 when any is open.
set -euo pipefail

PR="${1:?usage: check-pr-threads.sh <pr-number> [owner/repo]}"
REPO_SLUG="${2:-$(gh repo view --json nameWithOwner --jq '.nameWithOwner')}"
case "$REPO_SLUG" in
  */*) ;;
  *)
    echo "[check-pr-threads] repo slug inválido: '$REPO_SLUG' (esperado owner/repo)" >&2
    exit 2
    ;;
esac
OWNER="${REPO_SLUG%%/*}"
NAME="${REPO_SLUG##*/}"

DATA=$(gh api graphql \
  -f query='query($owner: String!, $name: String!, $pr: Int!) {
    repository(owner: $owner, name: $name) {
      pullRequest(number: $pr) {
        headRefOid
        reviewThreads(first: 100) {
          pageInfo { hasNextPage }
          nodes {
            isResolved
            isOutdated
            path
            comments(first: 1) { nodes { author { login } body } }
          }
        }
      }
    }
  }' -F owner="$OWNER" -F name="$NAME" -F pr="$PR")

if echo "$DATA" | jq -e '.errors' >/dev/null; then
  echo "[check-pr-threads] Erro na API do GitHub:" >&2
  echo "$DATA" | jq -r '.errors[].message' >&2
  exit 2
fi

if [ "$(echo "$DATA" | jq -r '.data.repository.pullRequest')" = "null" ]; then
  echo "[check-pr-threads] PR #$PR não encontrado no repositório $REPO_SLUG." >&2
  exit 2
fi

HAS_MORE=$(echo "$DATA" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage')
if [ "$HAS_MORE" = "true" ]; then
  echo "[check-pr-threads] PR tem mais de 100 threads; scan parcial não vale como gate" >&2
  exit 2
fi

HEAD_SHA=$(echo "$DATA" | jq -r '.data.repository.pullRequest.headRefOid[0:9] // "unknown"')
TOTAL=$(echo "$DATA" | jq '.data.repository.pullRequest.reviewThreads.nodes | length')
UNRESOLVED=$(echo "$DATA" | jq '[.data.repository.pullRequest.reviewThreads.nodes[]? | select(.isResolved == false)] | length')

echo "[check-pr-threads] PR #$PR ($REPO_SLUG) head=$HEAD_SHA threads=$TOTAL resolved=$((TOTAL - UNRESOLVED)) unresolved=$UNRESOLVED"

if [ "$UNRESOLVED" -gt 0 ]; then
  echo "$DATA" | jq -r '.data.repository.pullRequest.reviewThreads.nodes[]?
    | select(.isResolved == false)
    | "[open] " + .path + " (" + (.comments.nodes[0].author.login? // "?") + "): "
      + ((.comments.nodes[0].body? // "") | gsub("[\\n\\r]"; " ") | .[0:120])'
  exit 1
fi

echo "[check-pr-threads] OK: nenhuma thread de review em aberto."
