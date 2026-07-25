from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


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


def build_compose_command(service: str, cli_args: Sequence[str]) -> list[str]:
    """Assemble `docker compose run --rm <service> python -m src.cli ...`."""
    return [
        "docker",
        "compose",
        "run",
        "--rm",
        service,
        "python",
        "-m",
        "src.cli",
        *cli_args,
    ]


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


def build_process_batch_command(batch_id: str) -> list[str]:
    return build_compose_command(
        "ocr-parser",
        [
            "process-batch",
            "--manifest",
            f"/data/discovery/{batch_id}/crawled_products.csv",
            "--batch-id",
            batch_id,
        ],
    )


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
            )

    def start(self, step: str, command: list[str]) -> JobStatus:
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
            )
        thread = threading.Thread(
            target=self._run,
            args=(command,),
            daemon=True,
            name=f"console-job-{step}",
        )
        thread.start()
        return self.status()

    def _append_log(self, text: str) -> None:
        with self._lock:
            self._status.log += text

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
        except Exception as error:  # noqa: BLE001
            with self._lock:
                self._status.finished_at = time.time()
                self._status.state = JobState.FAILED
                self._status.error = str(error)
                self._status.log += f"\n[console] failed to start: {error}\n"
        finally:
            self._process = None
