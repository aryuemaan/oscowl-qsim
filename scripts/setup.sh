#!/usr/bin/env bash
# One-time setup: Python venv + backend deps, frontend deps, .env file.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
cd "$ROOT"

SYS_PY="$(find_system_python)" || { echo "Python 3.10+ not found. Install Python 3.12 from python.org (tick 'Add to PATH')."; exit 1; }
command -v npm >/dev/null || { echo "Node.js not found. Install Node 22 LTS from nodejs.org."; exit 1; }

echo "==> Creating virtual environment in .venv (using: $SYS_PY)"
[ -d .venv ] || $SYS_PY -m venv .venv
source "$ROOT/scripts/_common.sh"   # re-resolve PY now that .venv exists

echo "==> Installing backend packages"
"$PY" -m pip install --upgrade pip >/dev/null
"$PY" -m pip install -r backend/requirements-dev.txt

echo "==> Installing frontend packages"
(cd frontend && npm install --no-audit --no-fund)

if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> Created .env from .env.example (add your GEMINI_API_KEY there to switch on Gemini)"
fi

echo
echo "Setup complete. Next:"
echo "  bash scripts/dev.sh        # start backend + frontend, then open http://localhost:5173"
echo "  bash scripts/test.sh       # run the test suite"
