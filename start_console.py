"""Cross-platform launcher for the Pipeline Console UI (Windows / macOS / Linux).

Default: run via Docker Compose (recommended).
Fallback: local uvicorn with --local.
Optional: start the administrator Dagster UI with --platform.

If Docker Desktop is not running, prompts to start it and waits until ready
(Windows / macOS).
"""

from __future__ import annotations

import argparse
import html
import json
import os
import platform
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = 8787
DEFAULT_DAGSTER_PORT = 3000
DEFAULT_HOST = "127.0.0.1"
DOCKER_WAIT_SECONDS = 120
DOCKER_POLL_INTERVAL = 3
TRUE_VALUES = {"1", "true", "yes", "on"}


def _open_browser(url: str, delay_seconds: float = 2.0) -> None:
    def _open() -> None:
        time.sleep(delay_seconds)
        try:
            webbrowser.open(url)
        except Exception as error:  # noqa: BLE001
            print(f"[console] Could not open browser: {error}")

    threading.Thread(target=_open, daemon=True).start()


@dataclass(frozen=True)
class _ServiceEndpoint:
    key: str
    label: str
    target_url: str
    probe_url: str


def _connecting_html(endpoint: _ServiceEndpoint) -> str:
    label = html.escape(endpoint.label)
    target_json = json.dumps(endpoint.target_url)
    probe_json = json.dumps(endpoint.probe_url)
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{label} 연결 중</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; min-height: 100vh; display: grid; place-items: center;
      color: #e5eef8; background:
        radial-gradient(circle at top, #17375e 0, #08111f 48%, #050a12 100%);
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(440px, calc(100% - 32px)); padding: 40px 32px;
      text-align: center; border: 1px solid #294564; border-radius: 20px;
      background: rgba(8, 20, 35, .88); box-shadow: 0 24px 70px #0008;
    }}
    .spinner {{
      width: 52px; height: 52px; margin: 0 auto 24px;
      border: 5px solid #24415e; border-top-color: #60a5fa;
      border-radius: 50%; animation: spin .85s linear infinite;
    }}
    h1 {{ margin: 0 0 12px; font-size: 25px; }}
    p {{ margin: 0; color: #9fb3c8; line-height: 1.6; }}
    #elapsed {{ margin-top: 18px; color: #6f8ca8; font-size: 13px; }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  </style>
</head>
<body>
  <main>
    <div class="spinner" aria-hidden="true"></div>
    <h1>{label} 연결 중</h1>
    <p>서비스를 준비하고 있습니다.<br>연결되면 자동으로 이동합니다.</p>
    <div id="elapsed">시작하는 중...</div>
  </main>
  <script>
    const targetUrl = {target_json};
    const probeUrl = {probe_json};
    const startedAt = Date.now();
    async function checkReady() {{
      try {{
        await fetch(probeUrl, {{mode: "no-cors", cache: "no-store"}});
        location.replace(targetUrl);
      }} catch (_error) {{
        const seconds = Math.floor((Date.now() - startedAt) / 1000);
        document.getElementById("elapsed").textContent =
          `${{seconds}}초째 기다리는 중...`;
        setTimeout(checkReady, 800);
      }}
    }}
    setTimeout(checkReady, 200);
  </script>
</body>
</html>
"""


class _ConnectingPageServer:
    def __init__(self, endpoints: list[_ServiceEndpoint]) -> None:
        self._endpoints = {endpoint.key: endpoint for endpoint in endpoints}
        endpoint_map = self._endpoints

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                query = parse_qs(urlparse(self.path).query)
                key = query.get("service", [""])[0]
                endpoint = endpoint_map.get(key)
                if endpoint is None:
                    self.send_error(404)
                    return
                body = _connecting_html(endpoint).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args) -> None:
                return

        self._server = ThreadingHTTPServer((DEFAULT_HOST, 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
        )
        self._thread.start()

    def url(self, service_key: str) -> str:
        port = self._server.server_address[1]
        return f"http://{DEFAULT_HOST}:{port}/?{urlencode({'service': service_key})}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


def _open_connecting_pages(
    endpoints: list[_ServiceEndpoint],
) -> _ConnectingPageServer | None:
    try:
        server = _ConnectingPageServer(endpoints)
    except OSError as error:
        print(f"[console] Could not start connecting page: {error}")
        for endpoint in endpoints:
            _open_browser(endpoint.target_url)
        return None
    for endpoint in endpoints:
        _open_browser(server.url(endpoint.key), delay_seconds=0)
    return server


def _dotenv_flag(
    name: str,
    *,
    dotenv_path: Path | None = None,
) -> bool:
    environment_value = os.environ.get(name)
    if environment_value is not None:
        return environment_value.strip().lower() in TRUE_VALUES

    path = dotenv_path or ROOT / ".env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError, UnicodeError):
        return False

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        key, separator, value = stripped.partition("=")
        if separator and key.strip() == name:
            normalized = value.strip().strip("\"'").lower()
            return normalized in TRUE_VALUES
    return False


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


def _run_docker(
    port: int,
    *,
    no_browser: bool,
    assume_yes: bool,
    platform_mode: bool = False,
    dagster_port: int = DEFAULT_DAGSTER_PORT,
) -> int:
    if not ensure_docker_ready(assume_yes=assume_yes):
        return 1

    url = f"http://127.0.0.1:{port}/"
    print()
    print(" Pipeline Console (Docker)")
    print(f" {url}")
    if platform_mode:
        print(" Dagster (platform operator)")
        print(f" http://127.0.0.1:{dagster_port}/")
    print(" Stop: Ctrl+C")
    print()

    connecting_server = None
    if not no_browser:
        endpoints = [
            _ServiceEndpoint(
                key="console",
                label="Pipeline Console",
                target_url=url,
                probe_url=f"http://127.0.0.1:{port}/health",
            )
        ]
        if platform_mode:
            endpoints.append(
                _ServiceEndpoint(
                    key="dagster",
                    label="Dagster",
                    target_url=f"http://127.0.0.1:{dagster_port}/",
                    probe_url=f"http://127.0.0.1:{dagster_port}/server_info",
                )
            )
        connecting_server = _open_connecting_pages(endpoints)

    env = os.environ.copy()
    env["CONSOLE_PORT"] = str(port)
    env["DAGSTER_PORT"] = str(dagster_port)
    # Nested compose must resolve ./apps/... against the real host path.
    env["HOST_PROJECT_DIR"] = str(ROOT.resolve()).replace("\\", "/")
    platform_started = False
    try:
        if platform_mode:
            platform_result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "--profile",
                    "platform",
                    "up",
                    "-d",
                    "--build",
                    "dagster",
                ],
                cwd=str(ROOT),
                env=env,
                check=False,
            )
            if platform_result.returncode != 0:
                return platform_result.returncode
            platform_started = True

        cmd = ["docker", "compose", "up", "--build", "console"]
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
    finally:
        if platform_started:
            subprocess.call(
                ["docker", "compose", "--profile", "platform", "stop", "dagster"],
                cwd=str(ROOT),
            )
        if connecting_server is not None:
            connecting_server.close()


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

    connecting_server = None
    if not no_browser:
        connecting_server = _open_connecting_pages(
            [
                _ServiceEndpoint(
                    key="console",
                    label="Pipeline Console",
                    target_url=url,
                    probe_url=f"http://{host}:{port}/health",
                )
            ]
        )

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
    finally:
        if connecting_server is not None:
            connecting_server.close()


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
    platform_group = parser.add_mutually_exclusive_group()
    platform_group.add_argument(
        "--platform",
        action="store_true",
        help="Start Dagster with Console, overriding local .env",
    )
    platform_group.add_argument(
        "--console-only",
        action="store_true",
        help="Do not start Dagster, overriding local .env",
    )
    parser.add_argument(
        "--dagster-port",
        type=int,
        default=DEFAULT_DAGSTER_PORT,
        help=f"Dagster UI port with --platform (default: {DEFAULT_DAGSTER_PORT})",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Start Docker Desktop without prompting when it is not running",
    )
    args = parser.parse_args(argv)
    os.chdir(ROOT)
    platform_mode = args.platform or (
        not args.console_only and _dotenv_flag("CONSOLE_PLATFORM_MODE")
    )

    if args.local:
        if platform_mode:
            parser.error("--platform is available in Docker mode only")
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
        platform_mode=platform_mode,
        dagster_port=args.dagster_port,
    )


if __name__ == "__main__":
    raise SystemExit(main())
