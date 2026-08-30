from __future__ import annotations

import os
import sys
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import get_settings

_EXECUTOR_LOCK = threading.Lock()
_ACTIVE_RUNS: set[str] = set()


def _normalizer_candidates() -> list[Path]:
    settings = get_settings()
    candidates = [
        settings.project_root / "apps" / "normalizer",
        Path("/workspace/apps/normalizer"),
    ]
    file_path = Path(__file__).resolve()
    if len(file_path.parents) > 3:
        candidates.append(file_path.parents[3] / "apps" / "normalizer")
    normalizer_src = os.getenv("NORMALIZER_SRC", "").strip()
    if normalizer_src:
        candidates.append(Path(normalizer_src).expanduser().parent)
    return candidates


def _ensure_normalizer_src() -> Path:
    for candidate in _normalizer_candidates():
        if candidate.is_dir():
            path = str(candidate)
            if path not in sys.path:
                sys.path.insert(0, path)
            return candidate
    raise RuntimeError("normalizer src path not found for PipelineService")


def clear_pipeline_service_cache() -> None:
    get_pipeline_service.cache_clear()


def _import_normalizer_pipeline():
    """Load normalizer_pipeline without clobbering the console ``src`` package."""
    _ensure_normalizer_src()
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "src" or name.startswith("src.")
    }
    for name in saved_modules:
        del sys.modules[name]
    try:
        from src.normalizer_pipeline.service import PipelineService
        from src.normalizer_pipeline.store import build_pipeline_store

        return PipelineService, build_pipeline_store
    finally:
        for name in list(sys.modules):
            if name == "src" or name.startswith("src."):
                del sys.modules[name]
        sys.modules.update(saved_modules)


@lru_cache(maxsize=1)
def get_pipeline_service():
    settings = get_settings()
    database_url = os.getenv("DATABASE_URL", "").strip() or None
    PipelineService, build_pipeline_store = _import_normalizer_pipeline()
    store = build_pipeline_store(database_url)
    service = PipelineService.create(
        store=store,
        data_root=settings.datasets_root,
        outcome_root=settings.outcome_root,
        code_version=os.getenv("PIPELINE_CODE_VERSION", "dev"),
    )
    service.recover_stale_runs()
    return service


def schedule_run_execution(*, run_id: str, member: str) -> None:
    with _EXECUTOR_LOCK:
        if run_id in _ACTIVE_RUNS:
            return
        _ACTIVE_RUNS.add(run_id)

    def _runner() -> None:
        try:
            service = get_pipeline_service()
            service.execute_run(run_id, member=member)
        finally:
            with _EXECUTOR_LOCK:
                _ACTIVE_RUNS.discard(run_id)

    thread = threading.Thread(target=_runner, name=f"pipeline-run-{run_id}", daemon=True)
    thread.start()


def pipeline_error_response(error: Exception) -> tuple[int, dict[str, Any]]:
    code = getattr(error, "error_code", "PIPELINE_ERROR")
    return 400, {"error_code": code, "message": str(error)}
