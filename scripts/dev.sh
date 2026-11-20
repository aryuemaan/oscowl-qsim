#!/usr/bin/env bash
# Start backend and frontend together. Press Ctrl+C to stop both.
# (Prefer two terminals? Run scripts/run-backend.sh and scripts/run-frontend.sh separately.)
set -euo pipefail
source "$(dirname "$0")/_common.sh"
need_venv
bash "$ROOT/scripts/run-backend.sh" &
BACK=$!
trap 'kill $BACK 2>/dev/null || true' EXIT INT TERM
sleep 2
echo
echo "  Backend : http://localhost:8000/api/docs"
echo "  App     : http://localhost:5173"
echo
bash "$ROOT/scripts/run-frontend.sh"
