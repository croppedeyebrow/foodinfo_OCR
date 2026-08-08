from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import use_app


@pytest.fixture()
def normalizer_src() -> Path:
    return use_app("normalizer")


def test_status_transition_rules(normalizer_src: Path) -> None:
    from src.metadata.models import RunStatus, validate_status_transition

    validate_status_transition(RunStatus.PENDING, RunStatus.RUNNING)
    validate_status_transition(RunStatus.RUNNING, RunStatus.SUCCEEDED)
    validate_status_transition(RunStatus.SUCCEEDED, RunStatus.SUCCEEDED)
    with pytest.raises(ValueError, match="invalid status transition"):
        validate_status_transition(RunStatus.SUCCEEDED, RunStatus.RUNNING)


def test_pipeline_run_requires_sha256_config_hash(normalizer_src: Path) -> None:
    from src.metadata.models import PipelineRunCreate, TriggerType

    with pytest.raises(ValidationError):
        PipelineRunCreate(
            run_id="run-1",
            pipeline_name="test",
            trigger_type=TriggerType.MANUAL,
            code_version="test-code",
            config_hash="not-a-hash",
        )


def test_migrations_are_versioned_and_have_rollback(normalizer_src: Path) -> None:
    from src.metadata.migrations import default_migrations_dir, discover_migrations

    migrations = discover_migrations()
    assert [item.version for item in migrations] == ["0001"]
    assert all(len(item.checksum) == 64 for item in migrations)
    assert (
        default_migrations_dir() / "0001_pipeline_metadata.down.sql"
    ).is_file()


def test_dagster_boundary_returns_primitive_metadata(normalizer_src: Path) -> None:
    from src.metadata.dagster_adapter import artifact_materialization_metadata
    from src.metadata.models import PipelineArtifactCreate

    artifact = PipelineArtifactCreate(
        artifact_id="artifact-1",
        run_id="run-1",
        step_key="step-1",
        logical_name="silver",
        path="/data/silver/a.parquet",
        format="PARQUET",
        schema_version="1.0.0",
        checksum="a" * 64,
        row_count=3,
        byte_size=100,
        code_version="git-sha",
    )
    metadata = artifact_materialization_metadata(artifact)
    assert metadata["artifact_id"] == "artifact-1"
    assert metadata["checksum"] == "a" * 64
    assert metadata["row_count"] == 3
