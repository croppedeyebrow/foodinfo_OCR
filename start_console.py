"""Cross-platform launcher for the Pipeline Console UI (Windows / macOS / Linux).

Default: run via Docker Compose (recommended).
Fallback: local uvicorn with --local.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = 8787
DEFAULT_HOST = "127.0.0.1"


def _open_browser(url: str, delay_seconds: float = 2.0) -> None:
    def _open() -> None:
        time.sleep(delay_seconds)
        try:
            webbrowser.open(url)
        except Exception as error:  # noqa: BLE001
            print(f"[console] Could not open browser: {error}")

    threading.Thread(target=_open, daemon=True).start()


def _run_docker(port: int, *, no_browser: bool) -> int:
    url = f"http://127.0.0.1:{port}/"
    print()
    print(" Pipeline Console (Docker)")
    print(f" {url}")
    print(" Stop: Ctrl+C")
    print()

    if not no_browser:
        _open_browser(url)

    env = os.environ.copy()
    env["CONSOLE_PORT"] = str(port)
    # Nested compose must resolve ./apps/... against the real host path.
    env["HOST_PROJECT_DIR"] = str(ROOT.resolve()).replace("\\", "/")
    cmd = [
        "docker",
        "compose",
        "up",
        "--build",
        "console",
    ]
    try:
        return subprocess.call(cmd, cwd=str(ROOT), env=env)
    except FileNotFoundError:
        print("[console] docker not found. Install Docker Desktop, or use --local.")
        return 1
    except KeyboardInterrupt:
        print("\n[console] Stopped.")
        subprocess.call(
            ["docker", "compose", "stop", "console"],
            cwd=str(ROOT),
        )
        return 0


def _run_local(port: int, host: str, *, no_browser: bool, no_reload: bool) -> int:
    import importlib.util

    def has_module(name: str) -> bool:
        return importlib.util.find_spec(name) is not None

    if not (has_module("fastapi") and has_module("uvicorn")):
        print("[console] Installing local dependencies...")
        req = ROOT / "apps" / "console" / "requirements.txt"
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req)],
            cwd=str(ROOT),
        )
        if result.returncode != 0:
            return result.returncode

    url = f"http://{host}:{port}/"
    print()
    print(" Pipeline Console (local)")
    print(f" {url}")
    print(" Stop: Ctrl+C")
    print()

    if not no_browser:
        _open_browser(url, delay_seconds=1.5)

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.main:app",
        "--app-dir",
        str(ROOT / "apps" / "console"),
        "--host",
        host,
        "--port",
        str(port),
    ]
    if not no_reload:
        cmd.append("--reload")

    try:
        return subprocess.call(cmd, cwd=str(ROOT))
    except KeyboardInterrupt:
        print("\n[console] Stopped.")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start Kurly Pipeline Console")
    parser.add_argument(
        "port",
        nargs="?",
        type=int,
        default=DEFAULT_PORT,
        help=f"Listen port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run with host Python/uvicorn instead of Docker",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host (--local only)")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser automatically",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable auto-reload (--local only)",
    )
    args = parser.parse_args(argv)
    os.chdir(ROOT)

    if args.local:
        return _run_local(
            args.port,
            args.host,
            no_browser=args.no_browser,
            no_reload=args.no_reload,
        )
    return _run_docker(args.port, no_browser=args.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
