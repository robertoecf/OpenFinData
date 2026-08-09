#!/usr/bin/env bash
# Deterministic pre-ship / pre-push gate for openfindata.
# Writes evidence to <git-common-dir>/openfindata-verify/preflight.ok

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd -P)"
READINESS_SCRIPT="${REPO_ROOT}/docs/agents/openfindata-ship/scripts/readiness.sh"
BASE_REF="origin/main"
MODE="push"
SKIP_READINESS=0

usage() {
  cat <<'USAGE'
Usage: bash scripts/ship/preflight.sh [--quick | --push | --ci] [--base <ref>] [--skip-readiness]

Modes:
  --quick   ruff format --check + ruff check
  --push    readiness (unless skipped) + full local gate  [default]
  --ci      full local gate without readiness (ci.yml unit parity)

Options:
  --base <ref>        merge base for readiness (default: origin/main)
  --skip-readiness    skip worktree/readiness checks
  -h, --help          show this message

Evidence:
  <git-common-dir>/openfindata-verify/preflight.ok
USAGE
}

log() { printf '[ship:preflight] %s\n' "$*"; }
fail() { log "FAIL $*"; exit 1; }

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --quick) MODE="quick"; shift ;;
      --push) MODE="push"; shift ;;
      --ci) MODE="ci"; shift ;;
      --base) BASE_REF="${2:?--base requires a ref}"; shift 2 ;;
      --skip-readiness) SKIP_READINESS=1; shift ;;
      -h | --help) usage; exit 0 ;;
      *) fail "unknown argument: $1" ;;
    esac
  done
}

repo_root() { git rev-parse --show-toplevel; }

git_common_dir() {
  git rev-parse --path-format=absolute --git-common-dir
}

head_sha() { git rev-parse HEAD; }

pick_python() {
  local checkout common_root
  checkout="$(repo_root)"
  common_root="$(cd "$(git_common_dir)/.." && pwd -P)"
  if [[ -x "${checkout}/.venv/bin/python" ]]; then
    printf '%s\n' "${checkout}/.venv/bin/python"
  elif [[ -x "${common_root}/.venv/bin/python" ]]; then
    printf '%s\n' "${common_root}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    fail "No Python interpreter. Run: python3 -m venv .venv && pip install -e '.[dev]'"
  fi
}

evidence_dir() {
  local dir
  dir="$(git_common_dir)/openfindata-verify"
  mkdir -p "$dir"
  printf '%s\n' "$dir"
}

write_preflight_evidence() {
  local dir sha root steps
  dir="$(evidence_dir)"
  sha="$(head_sha)"
  root="$(repo_root)"
  steps="$1"
  {
    printf 'command=%s\n' 'bash scripts/ship/preflight.sh'
    printf 'mode=%s\n' "$MODE"
    printf 'steps=%s\n' "$steps"
    printf 'sha=%s\n' "$sha"
    printf 'repo=%s\n' "$root"
    printf 'created_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >"${dir}/preflight.ok"
}

run_readiness() {
  if [[ "$SKIP_READINESS" == "1" ]]; then
    log "skip readiness (--skip-readiness)"
    return 0
  fi
  if [[ ! -f "$READINESS_SCRIPT" ]]; then
    fail "readiness script missing: $READINESS_SCRIPT"
  fi
  log "readiness ($BASE_REF)"
  bash "$READINESS_SCRIPT" "$BASE_REF"
}

run_step() {
  local label="$1"
  shift
  log "$label"
  "$@"
}

run_ruff() {
  local py="$1"
  run_step "ruff format --check" "$py" -m ruff format --check src tests scripts
  run_step "ruff check" "$py" -m ruff check src tests scripts
}

run_full_gate() {
  local py="$1"
  run_ruff "$py"
  run_step "mypy --strict" "$py" -m mypy src/findata
  run_step "pytest (no integration)" "$py" -m pytest -q
}

main() {
  parse_args "$@"
  cd "$(repo_root)"

  local py
  py="$(pick_python)"
  local steps=()

  case "$MODE" in
    quick)
      run_ruff "$py"
      steps+=(ruff)
      ;;
    push)
      run_readiness
      steps+=(readiness)
      run_full_gate "$py"
      steps+=(ruff mypy pytest)
      ;;
    ci)
      run_full_gate "$py"
      steps+=(ruff mypy pytest)
      ;;
    *)
      fail "unknown mode: $MODE"
      ;;
  esac

  local joined
  joined=$(IFS=,; echo "${steps[*]}")
  write_preflight_evidence "$joined"
  log "OK mode=$MODE sha=$(head_sha) evidence=$(evidence_dir)/preflight.ok"
}

main "$@"
