#!/usr/bin/env bash
# Dados Financeiros Abertos git guardrails
# Split of responsibility:
#   - Context  → worktree/branch ownership (root and main are inspect-only).
#   - Ruff     → formatting + base lint + AI guardrails.
#   - Mypy     → strict type checking.
#   - Pytest   → unit-test fast path (integration on scheduled CI).
#   - ggshield (opt-in) → secret leak detection.

set -euo pipefail

guardrails_log() {
  printf '\033[1;36m[guardrails]\033[0m %s\n' "$*" >&2
}

guardrails_warn() {
  printf '\033[1;33m[guardrails]\033[0m %s\n' "$*" >&2
}

guardrails_err() {
  printf '\033[1;31m[guardrails]\033[0m %s\n' "$*" >&2
}

guardrails_repo_root() {
  local common_git_dir
  common_git_dir="$(git rev-parse --path-format=absolute --git-common-dir)"
  cd "${common_git_dir}/.." && pwd -P
}

guardrails_current_checkout() {
  git rev-parse --show-toplevel
}

guardrails_current_branch() {
  git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "DETACHED"
}

guardrails_normalize_dir() {
  local path="${1%/}"

  if [[ -z "$path" ]]; then
    path="/"
  fi

  (
    cd "$path" 2>/dev/null && pwd -P
  ) || printf '%s\n' "$path"
}

guardrails_effective_home() {
  local home_dir="${HOME:-}"

  if [[ "$home_dir" == *[![:space:]]* && -d "$home_dir" ]]; then
    guardrails_normalize_dir "$home_dir"
    return 0
  fi

  (
    unset HOME
    cd ~ 2>/dev/null && pwd -P
  )
}

guardrails_branch_class() {
  local branch="${1:-}"
  case "$branch" in
    main)
      echo "main"
      ;;
    codex/*)
      echo "codex"
      ;;
    claude/*|cursor/*|session/claude-*|claude_code_*|worktree-claude_*)
      echo "claude"
      ;;
    DETACHED)
      echo "detached"
      ;;
    *)
      echo "other"
      ;;
  esac
}

guardrails_path_class() {
  local path="$1"
  local home_dir
  local normalized_path
  local repo_root
  home_dir="$(guardrails_effective_home || true)"
  normalized_path="$(guardrails_normalize_dir "$path")"
  repo_root="$(guardrails_normalize_dir "$(guardrails_repo_root)")"

  if [[ -n "$home_dir" && "$normalized_path" == "$home_dir/.posthog-code/worktrees/"* ]]; then
    echo "posthog-worktree"
  elif [[ -n "$home_dir" && "$normalized_path" == "$home_dir/.cursor/worktrees/"* ]]; then
    echo "cursor-worktree"
  elif [[ "$normalized_path" == "$repo_root" ]]; then
    echo "root"
  elif [[ "$normalized_path" == "$repo_root/.worktrees/codex-"* ]]; then
    echo "codex-worktree"
  elif [[ "$normalized_path" == "$repo_root/.claude/worktrees/"* ]]; then
    echo "claude-worktree"
  elif [[ "$normalized_path" == "$repo_root/.worktrees/"* ]]; then
    echo "manual-worktree"
  else
    echo "external"
  fi
}

guardrails_require_allowed_context() {
  local action="$1"
  local checkout_path
  local branch
  local branch_class
  local path_class

  if [[ "${OPENFINDATA_GUARDRAILS_BYPASS:-0}" == "1" ]]; then
    guardrails_warn "Bypassing openfindata git guardrails for ${action} because OPENFINDATA_GUARDRAILS_BYPASS=1."
    return 0
  fi

  checkout_path="$(guardrails_current_checkout)"
  branch="$(guardrails_current_branch)"
  branch_class="$(guardrails_branch_class "$branch")"
  path_class="$(guardrails_path_class "$checkout_path")"

  if [[ "$path_class" == "root" ]]; then
    guardrails_err "Blocked ${action}: the root checkout is orchestration-only."
    guardrails_err "Use a dedicated worktree: .claude/worktrees/*, .worktrees/codex-*, \$HOME/.cursor/worktrees/*, or \$HOME/.posthog-code/worktrees/*."
    return 1
  fi

  if [[ "$branch_class" == "main" ]]; then
    guardrails_err "Blocked ${action}: branch 'main' is integration-only."
    return 1
  fi

  if [[ "$branch_class" == "detached" ]]; then
    guardrails_err "Blocked ${action}: detached HEAD is not an allowed agent workspace."
    return 1
  fi

  case "$path_class" in
    codex-worktree)
      if [[ "$branch_class" != "codex" ]]; then
        guardrails_err "Blocked ${action}: Codex worktrees under .worktrees/codex-* must use codex/* branches."
        return 1
      fi
      ;;
    claude-worktree)
      if [[ "$branch_class" != "claude" ]]; then
        guardrails_err "Blocked ${action}: Claude worktrees under .claude/worktrees/* must use Claude-owned branches (claude/* or cursor/*)."
        return 1
      fi
      ;;
    posthog-worktree)
      if [[ "$branch_class" != "claude" ]]; then
        guardrails_err "Blocked ${action}: PostHog Code worktrees must use Claude-owned branches."
        return 1
      fi
      ;;
    cursor-worktree)
      if [[ "$branch_class" != "claude" ]]; then
        guardrails_err "Blocked ${action}: Cursor worktrees must use Claude-owned branches (claude/* or cursor/*)."
        return 1
      fi
      ;;
    manual-worktree)
      guardrails_warn "Working from a manually-named worktree. Prefer .worktrees/codex-* or .claude/worktrees/*."
      ;;
    external)
      guardrails_err "Blocked ${action}: agent work must run from .worktrees/*, .claude/worktrees/*, \$HOME/.cursor/worktrees/*, or \$HOME/.posthog-code/worktrees/*."
      return 1
      ;;
    *)
      guardrails_err "Blocked ${action}: unsupported checkout path '${checkout_path}'."
      return 1
      ;;
  esac

  return 0
}

guardrails_warn_post_checkout() {
  local checkout_path
  local branch
  local branch_class
  local path_class

  checkout_path="$(guardrails_current_checkout)"
  branch="$(guardrails_current_branch)"
  branch_class="$(guardrails_branch_class "$branch")"
  path_class="$(guardrails_path_class "$checkout_path")"

  if [[ "$path_class" == "root" && "$branch" != "main" ]]; then
    guardrails_warn "root checkout is on '${branch}', not 'main'."
    guardrails_warn "Treat the root checkout as read-only and move active work into a dedicated worktree."
  fi

  if [[ "$path_class" == "root" && "$branch_class" == "claude" ]]; then
    guardrails_warn "root checkout is on Claude-owned branch '${branch}'."
    guardrails_warn "Switch the root checkout back to 'main' and continue from .claude/worktrees/*."
  fi

  return 0
}

# Pick a usable python: worktree .venv, then repo-root .venv, then python3.
guardrails_python() {
  local checkout root
  checkout="$(guardrails_current_checkout)"
  root="$(guardrails_repo_root)"
  if [[ -x "${checkout}/.venv/bin/python" ]]; then
    printf '%s\n' "${checkout}/.venv/bin/python"
  elif [[ -x "${root}/.venv/bin/python" ]]; then
    printf '%s\n' "${root}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    guardrails_err "No Python interpreter found. Run 'python3 -m venv .venv && pip install -e .[dev]'."
    return 1
  fi
}

guardrails_staged_py_files() {
  git diff --cached --name-only --diff-filter=ACMR -- '*.py' || true
}

# ── pre-commit: fast lints against the staged diff only ──────────────
guardrails_pre_commit() {
  local py
  py="$(guardrails_python)" || return 1

  local files
  files="$(guardrails_staged_py_files)"
  if [[ -z "$files" ]]; then
    guardrails_log "no staged Python files — skipping Ruff"
  else
    guardrails_log "ruff check (staged only)"
    # shellcheck disable=SC2086
    "$py" -m ruff check $files

    guardrails_log "ruff format --check (staged only)"
    # shellcheck disable=SC2086
    "$py" -m ruff format --check $files
  fi

  if command -v ggshield >/dev/null 2>&1; then
    guardrails_log "ggshield secret scan"
    ggshield secret scan pre-commit
  else
    guardrails_warn "ggshield not installed — skipping secret scan. brew install gitguardian/tap/ggshield to enable."
  fi
}

# ── pre-push: the whole safety net before code leaves the machine ───
guardrails_pre_push() {
  local py
  py="$(guardrails_python)" || return 1

  guardrails_log "ruff format --check (entire tree)"
  "$py" -m ruff format --check src tests scripts

  guardrails_log "ruff check (entire tree)"
  "$py" -m ruff check src tests scripts

  guardrails_log "mypy --strict"
  "$py" -m mypy src/findata

  guardrails_log "pytest (unit + API, no integration)"
  "$py" -m pytest -q
}

# ── install hooks: copy into shared git-dir so all worktrees share them ──
guardrails_install_hooks() {
  local checkout_root
  local common_git_dir
  local install_dir
  local source_hooks

  checkout_root="$(guardrails_current_checkout)"
  common_git_dir="$(git rev-parse --path-format=absolute --git-common-dir)"
  install_dir="${common_git_dir}/openfindata-hooks"
  source_hooks="${checkout_root}/.githooks"

  if [[ ! -d "$source_hooks" ]]; then
    guardrails_err "No .githooks directory at ${source_hooks}. Aborting."
    return 1
  fi

  mkdir -p "$install_dir"
  cp "${source_hooks}/pre-commit" "${install_dir}/pre-commit"
  cp "${source_hooks}/pre-push" "${install_dir}/pre-push"
  cp "${source_hooks}/post-checkout" "${install_dir}/post-checkout"
  cp "${checkout_root}/scripts/git/guardrails.sh" "${install_dir}/guardrails.sh"
  chmod +x "${install_dir}/pre-commit" "${install_dir}/pre-push" "${install_dir}/post-checkout" "${install_dir}/guardrails.sh"

  git config core.hooksPath "${install_dir}"
  guardrails_log "core.hooksPath = ${install_dir}"
  guardrails_log "run 'git config --unset core.hooksPath' to disable."
}

guardrails_main() {
  local command="${1:-}"
  case "$command" in
    check-commit)
      guardrails_require_allowed_context "commit"
      ;;
    check-push)
      guardrails_require_allowed_context "push"
      ;;
    warn-post-checkout)
      guardrails_warn_post_checkout
      ;;
    pre-commit)
      guardrails_pre_commit
      ;;
    pre-push)
      guardrails_pre_push
      ;;
    install-hooks)
      guardrails_install_hooks
      ;;
    *)
      guardrails_err "Usage: guardrails.sh <check-commit|check-push|warn-post-checkout|pre-commit|pre-push|install-hooks>"
      return 2
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
  guardrails_main "$@"
fi
