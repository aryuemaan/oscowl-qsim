#!/usr/bin/env bash
# FastAPI dev server with auto-reload on http://localhost:8000 (API docs: /api/docs)
set -euo pipefail
source "$(dirname "$0")/_common.sh"
need_venv
cd "$ROOT/backend"
exec "$PY" -m uvicorn app.main:app --reload --port "${PORT:-8000}"
