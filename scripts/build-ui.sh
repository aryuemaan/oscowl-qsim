#!/usr/bin/env bash
# Build the React app into backend/static so one server (port 8000) serves UI + API.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
(cd "$ROOT/frontend" && npm run build)
rm -rf "$ROOT/backend/static"
cp -r "$ROOT/frontend/dist" "$ROOT/backend/static"
echo "Built. Start with: bash scripts/run-backend.sh  ->  http://localhost:8000"
