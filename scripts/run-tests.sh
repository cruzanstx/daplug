#!/bin/bash
# Run the full daplug test validation: every pytest suite plus the model
# registry drift check. Single source of truth for CI and the /release skill —
# both call this script so the suite list can never drift between them.
#
# Usage: ./scripts/run-tests.sh
#
# Suites run in separate pytest processes: each appends its own scripts/ dir to
# sys.path and imports modules by bare name (executor, router, ...), which
# collide if combined. Exits non-zero on the first failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-python3}"

# GitHub log grouping when running under Actions; no-ops locally. Both always
# return success so they never become the script's exit status.
begin_group() { [ -n "${GITHUB_ACTIONS:-}" ] && echo "::group::$1"; return 0; }
end_group() { [ -n "${GITHUB_ACTIONS:-}" ] && echo "::endgroup::"; return 0; }

SUITES=(
  skills/prompt-executor/tests
  skills/cli-detector/tests
  skills/config-reader/tests
  skills/sprint/tests
  skills/at-prompt-runner/tests
  scripts/tests
)

for suite in "${SUITES[@]}"; do
  begin_group "$suite"
  "$PYTHON" -m pytest "$suite" -v
  end_group
done

begin_group "model registry consistency"
"$PYTHON" scripts/manage-models.py check
end_group
