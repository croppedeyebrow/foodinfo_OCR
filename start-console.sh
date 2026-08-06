#!/usr/bin/env bash
# macOS / Linux — start Pipeline Console via Docker (no host Python required)
set -euo pipefail
cd "$(dirname "$0")"

PORT=8787
NO_BROWSER=0
LOCAL=0
ASSUME_YES=0
DOCKER_WAIT_SECONDS=120
DOCKER_POLL_INTERVAL=3

usage() {
  echo "Usage: bash start-console.sh [port] [--no-browser] [--local] [-y|--yes]"
  echo "  Default: docker compose up --build console (python not required)"
  echo "  --local: host uvicorn (needs python3)"
  echo "  -y: start Docker Desktop without prompting"
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
    -y|--yes)
      ASSUME_YES=1
      ;;
    ''|*[!0-9]*)
      if [[ "$arg" == --* ]] || [[ "$arg" == -* ]]; then
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

docker_engine_ready() {
  docker info >/dev/null 2>&1
}

start_docker_desktop() {
  case "$(uname -s)" in
    Darwin)
      if ! open -a Docker; then
        echo "[console] Failed to open Docker.app. Is Docker Desktop installed?" >&2
        return 1
      fi
      ;;
    Linux)
      echo "[console] Auto-start is for macOS/Windows Docker Desktop." >&2
      echo "  Start your Docker engine manually, then retry." >&2
      return 1
      ;;
    *)
      echo "[console] Unsupported OS for Docker Desktop auto-start." >&2
      return 1
      ;;
  esac
}

wait_for_docker_engine() {
  local deadline remaining
  deadline=$((SECONDS + DOCKER_WAIT_SECONDS))
  while (( SECONDS < deadline )); do
    if docker_engine_ready; then
      return 0
    fi
    remaining=$((deadline - SECONDS))
    echo "[console] Waiting for Docker Desktop engine... (${remaining}s left)"
    sleep "$DOCKER_POLL_INTERVAL"
  done
  return 1
}

ensure_docker_ready() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "[console] docker CLI not found. Install Docker Desktop." >&2
    echo "  Or with host Python: python3 start_console.py --local" >&2
    return 1
  fi

  if docker_engine_ready; then
    return 0
  fi

  echo "[console] Docker Desktop does not appear to be running."
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    answer=y
  else
    printf "Start Docker Desktop now? [y/N]: "
    read -r answer || answer=n
  fi
  case "${answer}" in
    y|Y|yes|YES) ;;
    *)
      echo "[console] Cancelled. Start Docker Desktop manually, then retry."
      return 1
      ;;
  esac

  if ! start_docker_desktop; then
    return 1
  fi

  echo "[console] Starting Docker Desktop. Waiting up to ${DOCKER_WAIT_SECONDS}s..."
  if wait_for_docker_engine; then
    echo "[console] Docker engine is ready."
    return 0
  fi

  echo "[console] Timed out waiting for Docker Desktop." >&2
  echo "  Open Docker Desktop, wait until Running, then retry." >&2
  return 1
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
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    extra+=(--yes)
  fi
  exec "$PY" start_console.py "$PORT" --local "${extra[@]}"
fi

ensure_docker_ready

echo
echo " Pipeline Console (Docker)"
echo " ${URL}"
echo " HOST_PROJECT_DIR=${HOST_PROJECT_DIR}"
echo " Stop: Ctrl+C"
echo

open_browser
exec docker compose up --build console
