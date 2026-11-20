#!/usr/bin/env bash
# React dev server on http://localhost:5173 (proxies /api to the backend on :8000)
set -euo pipefail
source "$(dirname "$0")/_common.sh"
cd "$ROOT/frontend"
exec npm run dev
