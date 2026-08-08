"""Typed metadata records shared by CLI, repository, and Dagster adapters."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"


class TriggerType(str, Enum):
    MANUAL = "MANUAL"
    CONSOLE = "CONSOLE"
    DAGSTER = "DAGSTER"
    SCHEDULE = "SCHEDULE"
    EXTERNAL_SUBMISSION = "EXTERNAL_SUBMISSION"


class QualitySeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


TERMINAL_STATUSES = frozenset(
    {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.PARTIAL,
        RunStatus.CANCELLED,
    }
)

ALLOWED_STATUS_TRANSITIONS = {
    RunStatus.PENDING: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: TERMINAL_STATUSES,
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.PARTIAL: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


def validate_status_transition(current: RunStatus, target: RunStatus) -> None:
    if current == target:
        return
    if target not in ALLOWED_STATUS_TRANSITIONS[current]:
        raise ValueError(f"invalid status transition: {current.value} -> {target.value}")


class MetadataModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", use_enum_values=True, validate_default=True
    )


class PipelineRunCreate(MetadataModel):
    run_id: str = Field(min_length=1, max_length=255)
    pipeline_name: str = Field(min_length=1, max_length=255)
    batch_id: str | None = Field(default=None, max_length=255)
    trigger_type: TriggerType
    status: RunStatus = RunStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    code_version: str = Field(min_length=1, max_length=255)
    config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    error_summary: str | None = Field(default=None, max_length=4096)
    log_path: str | None = Field(default=None, max_length=2048)


class PipelineStepCreate(MetadataModel):
    run_id: str = Field(min_length=1, max_length=255)
    step_key: str = Field(min_length=1, max_length=255)
    attempt: int = Field(default=1, ge=1)
    status: RunStatus = RunStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    input_count: int = Field(default=0, ge=0)
    output_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    error_code: str | None = Field(default=None, max_length=255)
    error_message: str | None = Field(default=None, max_length=4096)
    log_path: str | None = Field(default=None, max_length=2048)


class PipelineArtifactCreate(MetadataModel):
    artifact_id: str = Field(min_length=1, max_length=255)
    run_id: str = Field(min_length=1, max_length=255)
    step_key: str = Field(min_length=1, max_length=255)
    step_attempt: int = Field(default=1, ge=1)
    logical_name: str = Field(min_length=1, max_length=255)
    path: str = Field(min_length=1, max_length=4096)
    format: str = Field(min_length=1, max_length=64)
    schema_version: str | None = Field(default=None, max_length=64)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    row_count: int | None = Field(default=None, ge=0)
    byte_size: int = Field(ge=0)
    code_version: str = Field(min_length=1, max_length=255)
    rule_version: str | None = Field(default=None, max_length=255)


class QualityResultCreate(MetadataModel):
    quality_result_id: str = Field(min_length=1, max_length=255)
    run_id: str = Field(min_length=1, max_length=255)
    artifact_id: str = Field(min_length=1, max_length=255)
    rule_id: str = Field(min_length=1, max_length=255)
    severity: QualitySeverity
    passed: bool
    observed_value: str | None = Field(default=None, max_length=4096)
    details: dict[str, object] = Field(default_factory=dict)


class ArtifactLineageCreate(MetadataModel):
    parent_artifact_id: str = Field(min_length=1, max_length=255)
    child_artifact_id: str = Field(min_length=1, max_length=255)
    relation_type: str = Field(default="DERIVED_FROM", min_length=1, max_length=64)
