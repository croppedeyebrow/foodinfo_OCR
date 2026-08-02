#!/usr/bin/env bash
# macOS / Linux — default: Docker Compose console service
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "[console] Docker not found. Install Docker Desktop, or run:" >&2
  echo "  python3 start_console.py --local" >&2
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "[console] python not found; using docker compose directly..."
  exec docker compose up --build console
fi

exec "$PY" start_console.py "$@"
