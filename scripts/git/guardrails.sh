#!/usr/bin/env bash
# Dados Financeiros Abertos git guardrails
# Inspired by wealthuman's biome+eslint pattern, adapted for Python/Ruff.
# Split of responsibility:
#   - Ruff   → formatting + base lint + AI guardrails (complexity, max-args, magic numbers).
#   - Mypy   → strict type checking.
#   - Pytest → unit-test fast path (integration tests run on CI).
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

# Pick a usable python: prefer the repo-local .venv, then the user's python3.
guardrails_python() {
  local root
  root="$(guardrails_repo_root)"
  if [[ -x "${root}/.venv/bin/python" ]]; then
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
    return 0
  fi

  guardrails_log "ruff check (staged only)"
  # shellcheck disable=SC2086  # intentional word-splitting for file list
  "$py" -m ruff check $files

  guardrails_log "ruff format --check (staged only)"
  # shellcheck disable=SC2086
  "$py" -m ruff format --check $files

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

  guardrails_log "ruff check (entire tree)"
  "$py" -m ruff check src tests

  guardrails_log "mypy --strict"
  "$py" -m mypy src

  guardrails_log "pytest (unit + API, no integration)"
  "$py" -m pytest -q
}

# ── install hooks: point core.hooksPath at .githooks ────────────────
guardrails_install_hooks() {
  local root
  root="$(guardrails_repo_root)"
  local target="${root}/.githooks"

  if [[ ! -d "$target" ]]; then
    guardrails_err "No .githooks directory at ${target}. Aborting."
    return 1
  fi

  chmod +x "${target}/pre-commit" "${target}/pre-push" "${target}/guardrails.sh" 2>/dev/null || true
  git config core.hooksPath "${target}"
  guardrails_log "core.hooksPath = ${target}"
  guardrails_log "run 'git config --unset core.hooksPath' to disable."
}

guardrails_main() {
  local command="${1:-}"
  case "$command" in
    pre-commit)    guardrails_pre_commit ;;
    pre-push)      guardrails_pre_push ;;
    install-hooks) guardrails_install_hooks ;;
    *)
      guardrails_err "Usage: guardrails.sh <pre-commit|pre-push|install-hooks>"
      return 2
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
  guardrails_main "$@"
fi
