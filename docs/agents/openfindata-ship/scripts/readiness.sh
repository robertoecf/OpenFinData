#!/usr/bin/env bash
set -u

base="${1:-origin/main}"

if ! top=$(git rev-parse --show-toplevel 2>/dev/null); then
  echo "[openfindata-ship] FAIL not inside a git repo" >&2
  exit 1
fi

cd "$top" || exit 1
branch=$(git branch --show-current 2>/dev/null || true)
git_dir=$(git rev-parse --path-format=absolute --git-dir 2>/dev/null || true)
common_dir=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
status=$(git status --porcelain)
fail=0
warn=0

say() { printf '%s\n' "$*"; }
ok() { say "[ok] $*"; }
warning() { say "[warn] $*"; warn=$((warn + 1)); }
failmsg() { say "[fail] $*"; fail=$((fail + 1)); }

say "[openfindata-ship] repo: $top"
say "[openfindata-ship] git-dir: ${git_dir:-unknown}"
say "[openfindata-ship] common-dir: ${common_dir:-unknown}"
say "[openfindata-ship] branch: ${branch:-detached}"
say "[openfindata-ship] base: $base"

if [ -z "$branch" ]; then
  failmsg "detached HEAD; ship should run from a named branch"
elif [ "$branch" = "main" ]; then
  failmsg "on main; use a dedicated agent branch/worktree before shipping"
else
  ok "not on main"
fi

if [ -n "$git_dir" ] && [ -n "$common_dir" ] && [ "$git_dir" = "$common_dir" ]; then
  failmsg "root checkout detected; use a dedicated linked worktree before shipping"
else
  ok "worktree checkout detected"
fi

if git rev-parse --verify "$base" >/dev/null 2>&1; then
  ok "$base exists"
  if git merge-base --is-ancestor "$base" HEAD 2>/dev/null; then
    ok "HEAD contains $base"
  else
    failmsg "HEAD is not based on $base; sync/rebase before shipping"
  fi
else
  warning "$base not available locally; run git fetch origin main"
fi

if [ -n "$status" ]; then
  failmsg "working tree has uncommitted changes; commit or exclude them before ship review/push"
else
  ok "working tree clean"
fi

if git rev-parse --verify "$base" >/dev/null 2>&1; then
  committed_changed=$(git diff --name-only "$base"...HEAD)
else
  committed_changed=$(git diff --name-only HEAD)
fi

working_changed=$(
  {
    git diff --name-only
    git diff --name-only --cached
    git ls-files --others --exclude-standard
  } | sort -u
)
changed=$(printf '%s\n%s\n' "$committed_changed" "$working_changed" | sed '/^$/d' | sort -u)

if [ -z "$changed" ] && [ -z "$status" ]; then
  warning "no changed files detected versus $base"
else
  say "[openfindata-ship] changed files (base diff + working tree):"
  printf '%s\n' "$changed" | sed '/^$/d; s/^/  - /'
fi

bad_artifacts=$(printf '%s\n' "$changed" | grep -E '(^|/)\.venv/|(^|/)\.(mypy|ruff|pytest)_cache/|(^|/)\.coverage|\.pyc$|(^|/)\.DS_Store$' || true)
if [ -n "$bad_artifacts" ]; then
  failmsg "generated/local artifacts are in the diff"
  printf '%s\n' "$bad_artifacts" | sed 's/^/  - /'
else
  ok "no obvious generated/local artifacts in diff"
fi

conflicts=0
while IFS= read -r file; do
  [ -n "$file" ] || continue
  [ -f "$file" ] || continue
  if grep -nE '^(<<<<<<<|>>>>>>>)' "$file" >/dev/null 2>&1; then
    say "[fail] conflict marker candidate: $file"
    conflicts=$((conflicts + 1))
  fi
done <<EOF_CHANGED
$changed
EOF_CHANGED
if [ "$conflicts" -gt 0 ]; then
  fail=$((fail + conflicts))
else
  ok "no conflict markers found in changed files"
fi

if [ -x "$top/.venv/bin/python" ] || command -v python3 >/dev/null 2>&1; then
  ok "python available"
else
  failmsg "no Python interpreter; create .venv and pip install -e '.[dev]'"
fi

if [ -x "$top/scripts/ship/preflight.sh" ] || [ -f "$top/scripts/ship/preflight.sh" ]; then
  ok "repo ship gate available: bash scripts/ship/preflight.sh"
else
  warning "scripts/ship/preflight.sh missing"
fi

if [ "$fail" -gt 0 ]; then
  say "[openfindata-ship] FAIL $fail blocking issue(s), $warn warning(s)"
  exit 1
fi

say "[openfindata-ship] OK with $warn warning(s). Resolve warnings or explain them before PR."
