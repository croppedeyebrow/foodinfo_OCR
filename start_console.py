"""Cross-platform launcher for the Pipeline Console UI (Windows / macOS / Linux).

Default: run via Docker Compose (recommended).
Fallback: local uvicorn with --local.

If Docker Desktop is not running, prompts to start it and waits until ready
(Windows / macOS).
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = 8787
DEFAULT_HOST = "127.0.0.1"
DOCKER_WAIT_SECONDS = 120
DOCKER_POLL_INTERVAL = 3


def _open_browser(url: str, delay_seconds: float = 2.0) -> None:
    def _open() -> None:
        time.sleep(delay_seconds)
        try:
            webbrowser.open(url)
        except Exception as error:  # noqa: BLE001
            print(f"[console] Could not open browser: {error}")

    threading.Thread(target=_open, daemon=True).start()


def _docker_cli_exists() -> bool:
    try:
        subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _docker_engine_ready() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _find_docker_desktop_windows() -> Path | None:
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    )
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [
        program_files / "Docker" / "Docker" / "Docker Desktop.exe",
        program_files_x86 / "Docker" / "Docker" / "Docker Desktop.exe",
        local_app_data / "Docker" / "Docker Desktop.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _start_docker_desktop() -> bool:
    system = platform.system()
    if system == "Darwin":
        result = subprocess.run(
            ["open", "-a", "Docker"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("[console] Failed to open Docker.app. Is Docker Desktop installed?")
            if result.stderr:
                print(result.stderr.strip())
            return False
        return True

    if system == "Windows":
        exe = _find_docker_desktop_windows()
        if exe is None:
            print(
                "[console] Docker Desktop.exe not found under Program Files. "
                "Install Docker Desktop or start it manually."
            )
            return False
        try:
            subprocess.Popen(  # noqa: S603
                [str(exe)],
                cwd=str(exe.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            print(f"[console] Failed to start Docker Desktop: {error}")
            return False
        return True

    print(
        "[console] Auto-start is supported on Windows/macOS Docker Desktop only. "
        "Start the Docker engine manually."
    )
    return False


def _prompt_yes_no(message: str) -> bool:
    try:
        answer = input(f"{message} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def _wait_for_docker_engine(*, timeout: int = DOCKER_WAIT_SECONDS) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _docker_engine_ready():
            return True
        remaining = max(0, int(deadline - time.time()))
        print(f"[console] Waiting for Docker Desktop engine... ({remaining}s left)")
        time.sleep(DOCKER_POLL_INTERVAL)
    return False


def ensure_docker_ready(*, assume_yes: bool = False) -> bool:
    """Ensure docker CLI exists and the engine is reachable; optionally start Desktop."""
    if not _docker_cli_exists():
        print("[console] docker CLI not found. Install Docker Desktop.")
        return False

    if _docker_engine_ready():
        return True

    print("[console] Docker Desktop does not appear to be running.")
    should_start = assume_yes or _prompt_yes_no("Start Docker Desktop now?")
    if not should_start:
        print("[console] Cancelled. Start Docker Desktop manually, then retry.")
        return False

    if not _start_docker_desktop():
        return False

    print(
        "[console] Starting Docker Desktop. "
        f"Waiting up to {DOCKER_WAIT_SECONDS}s for the engine..."
    )
    if _wait_for_docker_engine():
        print("[console] Docker engine is ready.")
        return True

    print(
        "[console] Timed out waiting for Docker Desktop. "
        "Open Docker Desktop, wait until it shows Running, then retry."
    )
    return False


def _run_docker(port: int, *, no_browser: bool, assume_yes: bool) -> int:
    if not ensure_docker_ready(assume_yes=assume_yes):
        return 1

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
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Start Docker Desktop without prompting when it is not running",
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
    return _run_docker(
        args.port,
        no_browser=args.no_browser,
        assume_yes=args.yes,
    )


if __name__ == "__main__":
    raise SystemExit(main())
