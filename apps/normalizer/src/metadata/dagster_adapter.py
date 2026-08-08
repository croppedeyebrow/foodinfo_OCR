"""Dependency-free boundary for the Dagster integration added in stage 05.

Dagster-specific objects stay outside the metadata repository. The next stage
may translate these primitive dictionaries into Dagster metadata values.
"""

from __future__ import annotations

from .models import PipelineArtifactCreate, PipelineRunCreate, TriggerType


def with_dagster_trigger(
    run: PipelineRunCreate, *, dagster_run_id: str
) -> PipelineRunCreate:
    payload = run.model_dump(mode="json")
    payload.update(
        {
            "trigger_type": TriggerType.DAGSTER,
            "log_path": run.log_path or f"dagster://run/{dagster_run_id}",
        }
    )
    return PipelineRunCreate.model_validate(payload)


def artifact_materialization_metadata(
    artifact: PipelineArtifactCreate,
) -> dict[str, str | int | None]:
    return {
        "artifact_id": artifact.artifact_id,
        "path": artifact.path,
        "format": artifact.format,
        "schema_version": artifact.schema_version,
        "checksum": artifact.checksum,
        "row_count": artifact.row_count,
        "byte_size": artifact.byte_size,
        "code_version": artifact.code_version,
        "rule_version": artifact.rule_version,
    }
