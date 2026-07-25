#!/usr/bin/env bash
# macOS / Linux launcher — wraps the cross-platform Python entrypoint.
set -euo pipefail
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "[console] python3/python not found. Install Python 3 and retry." >&2
  exit 1
fi

exec "$PY" start_console.py "$@"
