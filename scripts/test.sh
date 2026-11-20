#!/usr/bin/env bash
# Backend tests (pytest) + frontend type check.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
need_venv
(cd "$ROOT/backend" && "$PY" -m pytest "$@")
(cd "$ROOT/frontend" && npm run typecheck)
echo "All checks passed."
