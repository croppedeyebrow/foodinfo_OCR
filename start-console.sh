#!/usr/bin/env bash
# macOS / Linux — start Pipeline Console via Docker (no host Python required)
set -euo pipefail
cd "$(dirname "$0")"

PORT=8787
NO_BROWSER=0
LOCAL=0

usage() {
  echo "Usage: bash start-console.sh [port] [--no-browser] [--local]"
  echo "  Default: docker compose up --build console (python not required)"
  echo "  --local: host uvicorn (needs python3)"
}

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      usage
      exit 0
      ;;
    --no-browser)
      NO_BROWSER=1
      ;;
    --local)
      LOCAL=1
      ;;
    ''|*[!0-9]*)
      if [[ "$arg" == --* ]]; then
        echo "[console] Unknown option: $arg" >&2
        usage >&2
        exit 1
      fi
      ;;
    *)
      PORT="$arg"
      ;;
  esac
done

export HOST_PROJECT_DIR
HOST_PROJECT_DIR="$(pwd -P)"
export CONSOLE_PORT="$PORT"
URL="http://127.0.0.1:${PORT}/"

open_browser() {
  if [[ "$NO_BROWSER" -eq 1 ]]; then
    return
  fi
  (
    sleep 2
    if command -v open >/dev/null 2>&1; then
      open "$URL" >/dev/null 2>&1 || true
    elif command -v xdg-open >/dev/null 2>&1; then
      xdg-open "$URL" >/dev/null 2>&1 || true
    fi
  ) &
}

if [[ "$LOCAL" -eq 1 ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  elif command -v python >/dev/null 2>&1; then
    PY=python
  else
    echo "[console] --local needs python3 (or python) on PATH." >&2
    exit 1
  fi
  extra=()
  if [[ "$NO_BROWSER" -eq 1 ]]; then
    extra+=(--no-browser)
  fi
  exec "$PY" start_console.py "$PORT" --local "${extra[@]}"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[console] Docker not found. Install Docker Desktop." >&2
  echo "  Or with host Python: python3 start_console.py --local" >&2
  exit 1
fi

echo
echo " Pipeline Console (Docker)"
echo " ${URL}"
echo " HOST_PROJECT_DIR=${HOST_PROJECT_DIR}"
echo " Stop: Ctrl+C"
echo

open_browser
exec docker compose up --build console
