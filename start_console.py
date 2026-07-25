"""Cross-platform launcher for the Pipeline Console UI (Windows / macOS / Linux).

Run:
  Windows:  python start_console.py   (or start-console.cmd)
  macOS:    python3 start_console.py  (or bash start-console.sh)
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "apps" / "console" / "requirements.txt"
DEFAULT_PORT = 8787
DEFAULT_HOST = "127.0.0.1"


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _ensure_deps() -> None:
    if _has_module("fastapi") and _has_module("uvicorn"):
        return
    print("[console] Installing dependencies...")
    if not REQUIREMENTS.exists():
        raise SystemExit(f"[console] Missing requirements: {REQUIREMENTS}")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        raise SystemExit("[console] Failed to install requirements.")


def _open_browser(url: str, delay_seconds: float = 1.5) -> None:
    def _open() -> None:
        time.sleep(delay_seconds)
        try:
            webbrowser.open(url)
        except Exception as error:  # noqa: BLE001
            print(f"[console] Could not open browser: {error}")

    threading.Thread(target=_open, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start Kurly Pipeline Console")
    parser.add_argument(
        "port",
        nargs="?",
        type=int,
        default=DEFAULT_PORT,
        help=f"Listen port (default: {DEFAULT_PORT})",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser automatically",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable auto-reload",
    )
    args = parser.parse_args(argv)

    os.chdir(ROOT)
    _ensure_deps()

    url = f"http://{args.host}:{args.port}/"
    print()
    print(" Pipeline Console")
    print(f" {url}")
    print(" Stop: Ctrl+C")
    print()

    if not args.no_browser:
        _open_browser(url)

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.main:app",
        "--app-dir",
        str(ROOT / "apps" / "console"),
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if not args.no_reload:
        cmd.append("--reload")

    try:
        return subprocess.call(cmd, cwd=str(ROOT))
    except KeyboardInterrupt:
        print("\n[console] Stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
