from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ...metadata.models import PipelineArtifactCreate


@dataclass(slots=True)
class StageContext:
    batch_id: str
    member: str
    data_root: Path
    outcome_root: Path
    code_version: str
    attempt: int
    run_id: str = ""


@dataclass(slots=True)
class StageExecutionResult:
    input_count: int = 0
    output_count: int = 0
    failed_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    artifacts: list[PipelineArtifactCreate] = field(default_factory=list)
    progress_message: str | None = None


class StageService(Protocol):
    stage_key: str
    display_name: str
    prerequisites: tuple[str, ...]

    def check_prerequisites(self, context: StageContext) -> list[str]:
        """Return user-facing error messages when prerequisites are missing."""

    def execute(self, context: StageContext) -> StageExecutionResult:
        """Run stage business logic."""
