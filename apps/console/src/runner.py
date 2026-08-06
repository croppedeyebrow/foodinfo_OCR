from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence

from .progress import count_progress_events, progress_percent


class JobState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class JobStatus:
    state: JobState = JobState.IDLE
    step: str = ""
    command: list[str] = field(default_factory=list)
    log: str = ""
    exit_code: int | None = None
    started_at: float | None = None
    finished_at: float | None = None
    error: str = ""
    progress_total: int | None = None
    progress_done: int = 0
    progress_percent: int | None = None


def _compose_file_for_client() -> str | None:
    """Compose file path readable by the CLI process (container or host)."""
    explicit = os.getenv("COMPOSE_FILE_PATH", "").strip()
    if explicit:
        return explicit
    workspace = Path("/workspace/compose.yaml")
    if workspace.is_file():
        return str(workspace)
    return None


def _in_console_container() -> bool:
    return Path("/workspace/compose.yaml").is_file()


def _docker_bind_path(host_dir: str) -> str:
    """Convert a Windows host path to a Docker-style bind source."""
    normalized = host_dir.strip().replace("\\", "/")
    if not normalized:
        return ""
    if normalized.startswith("/"):
        return normalized.rstrip("/") or "/"
    if len(normalized) >= 2 and normalized[1] == ":":
        drive = normalized[0].lower()
        rest = normalized[2:]
        if not rest.startswith("/"):
            rest = f"/{rest}"
        return f"/{drive}{rest}".rstrip("/")
    return normalized.rstrip("/")


def _looks_like_usable_bind_root(path: str) -> bool:
    """Reject broken mountinfo paths like ``/Dev/...`` (missing drive prefix)."""
    normalized = path.strip().replace("\\", "/")
    if not normalized:
        return False
    # Windows bind without drive letter — writes into a Docker VM ghost dir.
    if normalized.startswith("/Dev/"):
        return False
    return True


def _workspace_mount_source() -> str | None:
    """VM path that backs /workspace (from mountinfo). Often unreliable on Desktop."""
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        parts = line.split()
        if len(parts) < 10 or parts[4] != "/workspace":
            continue
        root = parts[3]
        if root.startswith("/"):
            return root.rstrip("/") or "/"
    return None


def _workspace_bind_source_via_inspect() -> str | None:
    """Real host Source for /workspace via docker inspect (preferred)."""
    container_id = os.getenv("HOSTNAME", "").strip()
    if not container_id:
        return None
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                '{{range .Mounts}}{{if eq .Destination "/workspace"}}{{.Source}}{{end}}{{end}}',
                container_id,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    source = (result.stdout or "").strip().replace("\\", "/")
    return source.rstrip("/") if source else None


def _data_bind_root() -> str:
    """Host project root used for ``-v .../datasets:/data`` mounts."""
    explicit = os.getenv("DOCKER_BIND_ROOT", "").strip()
    if explicit and _looks_like_usable_bind_root(explicit):
        return explicit.replace("\\", "/").rstrip("/")

    inspected = _workspace_bind_source_via_inspect()
    if inspected and _looks_like_usable_bind_root(inspected):
        return inspected

    host_dir = os.getenv("HOST_PROJECT_DIR", "").strip()
    if host_dir:
        # Docker Desktop engine accepts Windows paths (C:/...) from Linux CLI.
        normalized = host_dir.replace("\\", "/").rstrip("/")
        if _looks_like_usable_bind_root(normalized) and (
            (len(normalized) >= 2 and normalized[1] == ":")
            or normalized.startswith("/run/desktop/mnt/host/")
            or (
                len(normalized) >= 3
                and normalized[0] == "/"
                and normalized[1].isalpha()
                and normalized[2] == "/"
            )
        ):
            if (
                len(normalized) >= 2
                and normalized[1] == ":"
            ):
                return normalized
            if normalized.startswith("/run/desktop/mnt/host/"):
                return normalized
            # /c/Dev/... → Desktop VM path
            return f"/run/desktop/mnt/host{normalized}"

    mounted = _workspace_mount_source()
    if mounted and _looks_like_usable_bind_root(mounted):
        return mounted

    converted = _docker_bind_path(host_dir)
    if converted and _looks_like_usable_bind_root(converted):
        if (
            len(converted) >= 3
            and converted[0] == "/"
            and converted[1].isalpha()
            and converted[2] == "/"
        ):
            return f"/run/desktop/mnt/host{converted}"
        return converted

    return "/workspace"


def build_docker_run_command(service: str, cli_args: Sequence[str]) -> list[str]:
    """Run crawler/ocr via `docker run` from inside the console container.

    Avoids `docker compose run` service volumes: relative `./apps/...` paths
    resolve to empty host dirs and wipe the image's /app/src.
    With a usable host bind root, mount live ``apps/*/src`` so new CLI
    commands (e.g. classify-images) work without rebuilding images.
    """
    project = os.getenv("COMPOSE_PROJECT_NAME", "kurly-freshness-pipeline")
    image = f"{project}-{service}"
    bind = _data_bind_root()
    mount_live_src = bind != "/workspace" and _looks_like_usable_bind_root(bind)

    crawler_memory = os.getenv("CRAWLER_MEMORY_LIMIT", "2g")
    crawler_shm = os.getenv("CRAWLER_SHM_SIZE", "512m")
    ocr_memory = os.getenv("OCR_MEMORY_LIMIT", "3g")
    ocr_shm = os.getenv("OCR_SHM_SIZE", "1g")

    command = ["docker", "run", "--rm"]
    if Path("/workspace/.env").is_file():
        command.extend(["--env-file", "/workspace/.env"])

    if service == "crawler":
        command.extend(
            [
                "--init",
                "--memory",
                crawler_memory,
                "--shm-size",
                crawler_shm,
            ]
        )
        if mount_live_src:
            command.extend(["-v", f"{bind}/apps/crawler/src:/app/src"])
        command.extend(["-v", f"{bind}/datasets:/data"])
    elif service == "ocr-parser":
        command.extend(
            [
                "--memory",
                ocr_memory,
                "--shm-size",
                ocr_shm,
                "--platform",
                "linux/amd64",
            ]
        )
        if mount_live_src:
            command.extend(["-v", f"{bind}/apps/ocr-parser/src:/app/src"])
        command.extend(
            [
                "-v",
                f"{bind}/datasets:/data",
                "-v",
                f"{bind}/outcome:/outcome",
                "-v",
                f"{bind}/contracts:/app/contracts:ro",
            ]
        )
    else:
        raise ValueError(f"unsupported service: {service}")

    command.extend([image, "python", "-m", "src.cli", *cli_args])
    return command


def build_compose_command(service: str, cli_args: Sequence[str]) -> list[str]:
    """Assemble job command: docker run (in console) or compose run (on host)."""
    if _in_console_container():
        return build_docker_run_command(service, cli_args)

    command = ["docker", "compose"]
    host_dir = os.getenv("HOST_PROJECT_DIR", "").strip()
    if host_dir:
        command.extend(["--project-directory", host_dir.replace("\\", "/")])
    compose_file = _compose_file_for_client()
    if compose_file:
        command.extend(["-f", compose_file])
    command.extend(
        [
            "run",
            "--rm",
            service,
            "python",
            "-m",
            "src.cli",
            *cli_args,
        ]
    )
    return command


def build_discover_urls_command(batch_id: str) -> list[str]:
    return build_compose_command(
        "crawler",
        [
            "discover-urls",
            "--input",
            "/data/input/product_urls.txt",
            "--batch-id",
            batch_id,
        ],
    )


def build_discover_search_command(
    batch_id: str,
    keyword: str,
    max_products: int,
    max_scrolls: int,
) -> list[str]:
    return build_compose_command(
        "crawler",
        [
            "discover-search",
            "--keyword",
            keyword,
            "--batch-id",
            batch_id,
            "--max-products",
            str(max_products),
            "--max-scrolls",
            str(max_scrolls),
        ],
    )


def build_discover_category_command(
    batch_id: str,
    *,
    category_code: str | None = None,
    category_url: str | None = None,
    max_products: int,
    max_scrolls: int,
) -> list[str]:
    args = ["discover-category", "--batch-id", batch_id]
    if category_code:
        args.extend(["--category-code", category_code])
    elif category_url:
        args.extend(["--category-url", category_url])
    else:
        raise ValueError("category_code or category_url is required")
    args.extend(
        [
            "--max-products",
            str(max_products),
            "--max-scrolls",
            str(max_scrolls),
        ]
    )
    return build_compose_command("crawler", args)


def build_collect_details_command(batch_id: str, *, force: bool = False) -> list[str]:
    args = [
        "collect-details",
        "--manifest",
        f"/data/discovery/{batch_id}/discovered_products.csv",
    ]
    if force:
        args.append("--force")
    return build_compose_command("crawler", args)


def build_classify_images_command(batch_id: str, *, force: bool = False) -> list[str]:
    args = [
        "classify-images",
        "--manifest",
        f"/data/discovery/{batch_id}/crawled_products.csv",
        "--batch-id",
        batch_id,
    ]
    if force:
        args.append("--force")
    return build_compose_command("ocr-parser", args)


def build_process_batch_command(
    batch_id: str,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[str]:
    args = [
        "process-batch",
        "--manifest",
        f"/data/discovery/{batch_id}/crawled_products.csv",
        "--batch-id",
        batch_id,
    ]
    if offset:
        args.extend(["--offset", str(offset)])
    if limit is not None:
        args.extend(["--limit", str(limit)])
    return build_compose_command("ocr-parser", args)


class JobRunner:
    """Single-job lock with in-memory log buffer."""

    def __init__(self, project_root: str | None = None) -> None:
        self._lock = threading.Lock()
        self._status = JobStatus()
        self._project_root = project_root
        self._process: subprocess.Popen[str] | None = None

    def status(self) -> JobStatus:
        with self._lock:
            return JobStatus(
                state=self._status.state,
                step=self._status.step,
                command=list(self._status.command),
                log=self._status.log,
                exit_code=self._status.exit_code,
                started_at=self._status.started_at,
                finished_at=self._status.finished_at,
                error=self._status.error,
                progress_total=self._status.progress_total,
                progress_done=self._status.progress_done,
                progress_percent=self._status.progress_percent,
            )

    def start(
        self,
        step: str,
        command: list[str],
        *,
        progress_total: int | None = None,
    ) -> JobStatus:
        with self._lock:
            if self._status.state == JobState.RUNNING:
                raise RuntimeError("A job is already running")
            self._status = JobStatus(
                state=JobState.RUNNING,
                step=step,
                command=list(command),
                log="",
                exit_code=None,
                started_at=time.time(),
                finished_at=None,
                error="",
                progress_total=progress_total,
                progress_done=0,
                progress_percent=progress_percent(0, progress_total),
            )
        thread = threading.Thread(
            target=self._run,
            args=(command,),
            daemon=True,
            name=f"console-job-{step}",
        )
        thread.start()
        return self.status()

    def _refresh_progress_locked(self) -> None:
        done = count_progress_events(self._status.step, self._status.log)
        total = self._status.progress_total
        if total is not None:
            done = min(done, total)
        if self._status.state in {JobState.SUCCEEDED, JobState.FAILED} and total:
            done = total if self._status.state == JobState.SUCCEEDED else min(done, total)
        self._status.progress_done = done
        self._status.progress_percent = progress_percent(done, total)

    def _append_log(self, text: str) -> None:
        with self._lock:
            self._status.log += text
            self._refresh_progress_locked()

    def _run(self, command: list[str]) -> None:
        try:
            process = subprocess.Popen(
                command,
                cwd=self._project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            self._process = process
            assert process.stdout is not None
            for line in process.stdout:
                self._append_log(line)
            exit_code = process.wait()
            with self._lock:
                self._status.exit_code = exit_code
                self._status.finished_at = time.time()
                self._status.state = (
                    JobState.SUCCEEDED if exit_code == 0 else JobState.FAILED
                )
                if exit_code != 0:
                    self._status.error = f"exit_code={exit_code}"
                self._refresh_progress_locked()
        except Exception as error:  # noqa: BLE001
            with self._lock:
                self._status.finished_at = time.time()
                self._status.state = JobState.FAILED
                self._status.error = str(error)
                self._status.log += f"\n[console] failed to start: {error}\n"
                self._refresh_progress_locked()
        finally:
            self._process = None
