# Shared helpers for the scripts in this folder (works in Git Bash on Windows, macOS and Linux).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$ROOT/.venv/Scripts/python.exe" ]; then
  PY="$ROOT/.venv/Scripts/python.exe"     # Windows venv layout
else
  PY="$ROOT/.venv/bin/python"             # macOS / Linux venv layout
fi

find_system_python() {
  for c in python3 python "py -3"; do
    if $c -c "import sys; assert sys.version_info >= (3, 10)" >/dev/null 2>&1; then echo "$c"; return 0; fi
  done
  return 1
}

need_venv() {
  if [ ! -x "$PY" ] && [ ! -f "$PY" ]; then
    echo "Python environment not found. Run: bash scripts/setup.sh" >&2
    exit 1
  fi
}
