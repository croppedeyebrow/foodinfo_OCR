from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from ..metadata.models import (
    ArtifactLineageCreate,
    PipelineArtifactCreate,
    PipelineRunCreate,
    PipelineStepCreate,
    QualityResultCreate,
    RunStatus,
    TriggerType,
)
from ..metadata.repository import MetadataRepository


class InMemoryPipelineStore:
    """Test double for pipeline metadata without PostgreSQL."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.steps: list[dict[str, Any]] = []
        self.artifacts: list[dict[str, Any]] = []
        self.lineage: list[dict[str, Any]] = []
        self.quality_results: list[dict[str, Any]] = []

    def create_run(self, record: PipelineRunCreate) -> dict[str, Any]:
        values = record.model_dump(mode="json")
        existing = self.runs.get(record.run_id)
        if existing is not None:
            return existing
        now = datetime.now().isoformat()
        row = {**values, "created_at": now, "updated_at": now}
        self.runs[record.run_id] = row
        return deepcopy(row)

    def transition_run(
        self,
        run_id: str,
        target: RunStatus,
        *,
        at: datetime | None = None,
        error_summary: str | None = None,
        log_path: str | None = None,
    ) -> dict[str, Any]:
        run = self.runs[run_id]
        run["status"] = target.value if hasattr(target, "value") else target
        if error_summary is not None:
            run["error_summary"] = error_summary
        if log_path is not None:
            run["log_path"] = log_path
        run["updated_at"] = datetime.now().isoformat()
        return deepcopy(run)

    def create_step(self, record: PipelineStepCreate) -> dict[str, Any]:
        values = record.model_dump(mode="json")
        for item in self.steps:
            if (
                item["run_id"] == record.run_id
                and item["step_key"] == record.step_key
                and item["attempt"] == record.attempt
            ):
                return deepcopy(item)
        now = datetime.now().isoformat()
        row = {**values, "created_at": now, "updated_at": now}
        self.steps.append(row)
        return deepcopy(row)

    def transition_step(
        self,
        run_id: str,
        step_key: str,
        attempt: int,
        target: RunStatus,
        *,
        at: datetime | None = None,
        input_count: int | None = None,
        output_count: int | None = None,
        failed_count: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        log_path: str | None = None,
    ) -> dict[str, Any]:
        for item in self.steps:
            if (
                item["run_id"] == run_id
                and item["step_key"] == step_key
                and item["attempt"] == attempt
            ):
                item["status"] = target.value if hasattr(target, "value") else target
                if input_count is not None:
                    item["input_count"] = input_count
                if output_count is not None:
                    item["output_count"] = output_count
                if failed_count is not None:
                    item["failed_count"] = failed_count
                if error_code is not None:
                    item["error_code"] = error_code
                if error_message is not None:
                    item["error_message"] = error_message
                if log_path is not None:
                    item["log_path"] = log_path
                item["updated_at"] = datetime.now().isoformat()
                return deepcopy(item)
        raise KeyError(f"step not found: {run_id}/{step_key}/{attempt}")

    def register_artifact(self, record: PipelineArtifactCreate) -> dict[str, Any]:
        values = record.model_dump(mode="json")
        for item in self.artifacts:
            if item["artifact_id"] == record.artifact_id:
                return deepcopy(item)
        now = datetime.now().isoformat()
        row = {**values, "created_at": now, "updated_at": now}
        self.artifacts.append(row)
        return deepcopy(row)

    def add_lineage(self, record: ArtifactLineageCreate) -> dict[str, Any]:
        values = record.model_dump(mode="json")
        self.lineage.append(values)
        return deepcopy(values)

    def record_quality_result(self, record: QualityResultCreate) -> dict[str, Any]:
        values = record.model_dump(mode="json")
        self.quality_results.append(values)
        return deepcopy(values)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run = self.runs.get(run_id)
        if run is None:
            return None
        return {
            "run": deepcopy(run),
            "steps": deepcopy(
                [item for item in self.steps if item["run_id"] == run_id]
            ),
            "artifacts": deepcopy(
                [item for item in self.artifacts if item["run_id"] == run_id]
            ),
            "quality_results": deepcopy(
                [item for item in self.quality_results if item["run_id"] == run_id]
            ),
        }

    def list_runs(
        self, *, batch_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        rows = list(self.runs.values())
        if batch_id is not None:
            rows = [item for item in rows if item.get("batch_id") == batch_id]
        rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return deepcopy(rows[:limit])

    def trace_ancestors(self, artifact_id: str) -> list[dict[str, Any]]:
        return []


def build_pipeline_store(database_url: str | None):
    if database_url:
        return MetadataRepository(database_url)
    return InMemoryPipelineStore()


def config_hash_for(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()
