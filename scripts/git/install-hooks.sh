#!/usr/bin/env bash
# Install Dados Financeiros Abertos git hooks into <git-common-dir>/openfindata-hooks/
# and point core.hooksPath there (shared by all worktrees). Idempotent.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/guardrails.sh"

guardrails_install_hooks
