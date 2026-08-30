from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..metadata.models import (
    PipelineRunCreate,
    PipelineStepCreate,
    RunStatus,
    TriggerType,
)
from .errors import (
    DuplicateRunError,
    PrerequisiteError,
    RetryNotAllowedError,
    RunNotFoundError,
    UnknownStageError,
)
from .stages import STAGE_REGISTRY
from .stages.base import StageContext, StageService
from .store import InMemoryPipelineStore, config_hash_for

KST = ZoneInfo("Asia/Seoul")
ACTIVE_STATUSES = {RunStatus.PENDING.value, RunStatus.RUNNING.value}
TERMINAL_FAILURE = {RunStatus.FAILED.value, RunStatus.CANCELLED.value}


@dataclass(slots=True)
class PipelineService:
    store: Any
    data_root: Path
    outcome_root: Path
    code_version: str
    stages: dict[str, StageService]
    _lock: threading.Lock

    @classmethod
    def create(
        cls,
        *,
        store: Any,
        data_root: Path,
        outcome_root: Path,
        code_version: str,
        stages: dict[str, StageService] | None = None,
    ) -> PipelineService:
        return cls(
            store=store,
            data_root=data_root,
            outcome_root=outcome_root,
            code_version=code_version,
            stages=stages or STAGE_REGISTRY,
            _lock=threading.Lock(),
        )

    def recover_stale_runs(self) -> int:
        recovered = 0
        for run in self.store.list_runs(limit=1000):
            if run.get("status") != RunStatus.RUNNING.value:
                continue
            self.store.transition_run(
                run["run_id"],
                RunStatus.FAILED,
                error_summary="프로세스 재시작으로 실행이 중단되었습니다.",
            )
            snapshot = self.store.get_run(run["run_id"])
            if snapshot is None:
                continue
            for step in snapshot["steps"]:
                if step.get("status") == RunStatus.RUNNING.value:
                    self.store.transition_step(
                        run["run_id"],
                        step["step_key"],
                        int(step["attempt"]),
                        RunStatus.FAILED,
                        error_code="PROCESS_RESTART",
                        error_message="프로세스 재시작으로 실행이 중단되었습니다.",
                    )
            recovered += 1
        return recovered

    def start_run(
        self,
        *,
        batch_id: str,
        member: str,
        stage_key: str,
        trigger_type: TriggerType = TriggerType.CONSOLE,
    ) -> dict[str, Any]:
        stage = self._stage(stage_key)
        context = StageContext(
            batch_id=batch_id,
            member=member,
            data_root=self.data_root,
            outcome_root=self.outcome_root,
            code_version=self.code_version,
            attempt=1,
        )
        prereq_errors = stage.check_prerequisites(context)
        if prereq_errors:
            raise PrerequisiteError(prereq_errors[0])

        with self._lock:
            if self._has_active_run(batch_id, stage_key):
                raise DuplicateRunError(batch_id, stage_key)
            attempt = self._next_attempt(batch_id, stage_key)
            run_id = self._run_id(batch_id, stage_key, attempt)
            config_hash = config_hash_for(batch_id, stage_key, str(attempt))
            self.store.create_run(
                PipelineRunCreate(
                    run_id=run_id,
                    pipeline_name=f"batch_stage:{stage_key}",
                    batch_id=batch_id,
                    trigger_type=trigger_type,
                    status=RunStatus.PENDING,
                    code_version=self.code_version,
                    config_hash=config_hash,
                )
            )
            self.store.create_step(
                PipelineStepCreate(
                    run_id=run_id,
                    step_key=stage_key,
                    attempt=attempt,
                    status=RunStatus.PENDING,
                )
            )
        snapshot = self.get_run(run_id)
        assert snapshot is not None
        return snapshot

    def execute_run(self, run_id: str, *, member: str) -> dict[str, Any]:
        raw_snapshot = self.store.get_run(run_id)
        if raw_snapshot is None:
            raise RunNotFoundError(run_id)
        run = raw_snapshot["run"]
        if run["status"] in {
            RunStatus.SUCCEEDED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        }:
            presented = self.get_run(run_id)
            assert presented is not None
            return presented

        step = self._primary_step(raw_snapshot)
        stage_key = step["step_key"]
        attempt = int(step["attempt"])
        stage = self._stage(stage_key)
        context = StageContext(
            batch_id=str(run["batch_id"]),
            member=member,
            data_root=self.data_root,
            outcome_root=self.outcome_root,
            code_version=self.code_version,
            attempt=attempt,
            run_id=run_id,
        )

        self.store.transition_run(run_id, RunStatus.RUNNING)
        self.store.transition_step(
            run_id, stage_key, attempt, RunStatus.RUNNING
        )
        result = stage.execute(context)
        for artifact in result.artifacts:
            payload = artifact.model_copy(update={"run_id": run_id})
            self.store.register_artifact(payload)

        if result.error_code or result.failed_count:
            self.store.transition_step(
                run_id,
                stage_key,
                attempt,
                RunStatus.FAILED,
                input_count=result.input_count,
                output_count=result.output_count,
                failed_count=result.failed_count or 1,
                error_code=result.error_code or "STAGE_FAILED",
                error_message=result.error_message or "stage execution failed",
            )
            self.store.transition_run(
                run_id,
                RunStatus.FAILED,
                error_summary=result.error_message,
            )
        else:
            self.store.transition_step(
                run_id,
                stage_key,
                attempt,
                RunStatus.SUCCEEDED,
                input_count=result.input_count,
                output_count=result.output_count,
                failed_count=result.failed_count,
            )
            self.store.transition_run(run_id, RunStatus.SUCCEEDED)

        final_snapshot = self.get_run(run_id)
        assert final_snapshot is not None
        return final_snapshot

    def retry_run(self, run_id: str, *, member: str) -> dict[str, Any]:
        raw_snapshot = self.store.get_run(run_id)
        if raw_snapshot is None:
            raise RunNotFoundError(run_id)
        run = raw_snapshot["run"]
        if run["status"] not in TERMINAL_FAILURE:
            raise RetryNotAllowedError("실패 또는 취소된 run만 재실행할 수 있습니다.")
        step = self._primary_step(raw_snapshot)
        return self.start_run(
            batch_id=str(run["batch_id"]),
            member=member,
            stage_key=step["step_key"],
        )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        snapshot = self.store.get_run(run_id)
        if snapshot is None:
            return None
        return self._present_run(snapshot)

    def get_batch_status(self, batch_id: str) -> dict[str, Any]:
        runs = self.store.list_runs(batch_id=batch_id, limit=200)
        stages: list[dict[str, Any]] = []
        for stage_key, stage in self.stages.items():
            stage_runs = [
                item
                for item in runs
                if item.get("pipeline_name") == f"batch_stage:{stage_key}"
            ]
            latest = stage_runs[0] if stage_runs else None
            latest_snapshot = (
                self.get_run(str(latest["run_id"])) if latest is not None else None
            )
            stages.append(
                {
                    "stage_key": stage_key,
                    "display_name": stage.display_name,
                    "prerequisites": list(stage.prerequisites),
                    "status": self._stage_status(latest_snapshot),
                    "latest_run_id": latest["run_id"] if latest else None,
                    "latest_run": latest_snapshot,
                }
            )
        return {"batch_id": batch_id, "stages": stages}

    def list_stage_keys(self) -> list[dict[str, str]]:
        return [
            {
                "stage_key": stage.stage_key,
                "display_name": stage.display_name,
            }
            for stage in self.stages.values()
        ]

    def _stage(self, stage_key: str) -> StageService:
        stage = self.stages.get(stage_key)
        if stage is None:
            raise UnknownStageError(stage_key)
        return stage

    def _run_id(self, batch_id: str, stage_key: str, attempt: int) -> str:
        return f"batch:{batch_id}:{stage_key}:{attempt}"

    def _next_attempt(self, batch_id: str, stage_key: str) -> int:
        runs = self.store.list_runs(batch_id=batch_id, limit=200)
        attempts = [
            int(item["run_id"].rsplit(":", 1)[-1])
            for item in runs
            if item.get("pipeline_name") == f"batch_stage:{stage_key}"
            and str(item["run_id"]).startswith(f"batch:{batch_id}:{stage_key}:")
        ]
        return (max(attempts) if attempts else 0) + 1

    def _has_active_run(self, batch_id: str, stage_key: str) -> bool:
        for run in self.store.list_runs(batch_id=batch_id, limit=200):
            if run.get("pipeline_name") != f"batch_stage:{stage_key}":
                continue
            if run.get("status") in ACTIVE_STATUSES:
                return True
        return False

    def _primary_step(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        steps = snapshot.get("steps") or []
        if not steps:
            raise RunNotFoundError(str(snapshot["run"]["run_id"]))
        return sorted(steps, key=lambda item: int(item["attempt"]), reverse=True)[0]

    def _stage_status(self, snapshot: dict[str, Any] | None) -> str:
        if snapshot is None:
            return "READY"
        if "run" in snapshot:
            run_status = snapshot["run"]["status"]
        else:
            run_status = snapshot.get("status")
        if run_status == RunStatus.SUCCEEDED.value:
            return "SUCCEEDED"
        if run_status == RunStatus.RUNNING.value:
            return "RUNNING"
        if run_status == RunStatus.PENDING.value:
            return "PENDING"
        if run_status == RunStatus.FAILED.value:
            return "FAILED"
        return str(run_status)

    def _present_run(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        run = dict(snapshot["run"])
        steps = [dict(item) for item in snapshot.get("steps", [])]
        artifacts = [dict(item) for item in snapshot.get("artifacts", [])]
        step = steps[-1] if steps else None
        return {
            "run_id": run["run_id"],
            "batch_id": run.get("batch_id"),
            "pipeline_name": run.get("pipeline_name"),
            "status": run.get("status"),
            "error_summary": run.get("error_summary"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "code_version": run.get("code_version"),
            "steps": steps,
            "artifacts": artifacts,
            "progress": {
                "input_count": step.get("input_count", 0) if step else 0,
                "output_count": step.get("output_count", 0) if step else 0,
                "failed_count": step.get("failed_count", 0) if step else 0,
                "error_code": step.get("error_code") if step else None,
                "error_message": step.get("error_message") if step else None,
            },
        }
