#!/usr/bin/env bash
# Dense state vector vs MPS benchmark. Pass --quick for a fast run.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
need_venv
cd "$ROOT"
"$PY" benchmarks/benchmark.py "$@"
