from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from conftest import use_app

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contracts"
CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"


def _database_url() -> str:
    value = os.getenv("PIPELINE_TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not value:
        pytest.skip("local PostgreSQL DATABASE_URL is not configured")
    return value


def _accepted_fixture(tmp_path: Path, batch_id: str) -> tuple[Path, str]:
    from src.submission import submit_collection_batch

    member = "jaeseong"
    data_root = tmp_path / "datasets"
    outcome_root = tmp_path / "outcome"
    discovery = data_root / "discovery" / batch_id
    outcome = outcome_root / member / batch_id
    discovery.mkdir(parents=True)
    outcome.mkdir(parents=True)
    (discovery / "discovered_products.csv").write_text(
        "original_product_id\n1000001\n1000002\n", encoding="utf-8-sig"
    )
    (discovery / "crawled_products.csv").write_text(
        "original_product_id\n1000001\n1000002\n", encoding="utf-8-sig"
    )
    (discovery / "image_text_check.csv").write_text(
        "image_path,text_presence\na.jpg,HAS_TEXT\nb.jpg,NO_TEXT\n",
        encoding="utf-8-sig",
    )
    products = (FIXTURES / "sample_products.csv").read_text(encoding="utf-8-sig")
    products = products.replace("20260808-jaeseong-001", batch_id)
    (outcome / "products.csv").write_text(products, encoding="utf-8-sig")
    submit_collection_batch(
        data_root=data_root,
        outcome_root=outcome_root,
        batch_id=batch_id,
        member=member,
        contracts_dir=CONTRACTS_DIR,
    )
    return data_root, member


def test_dagster_collection_partition_rerun_is_idempotent(
    tmp_path: Path,
) -> None:
    dg = pytest.importorskip("dagster")
    use_app("normalizer")
    from orchestration.assets import (
        kurly_bronze_validated,
        kurly_collection_submission,
    )
    from orchestration.partitions import collection_batch_partitions
    from orchestration.resources import (
        ArtifactStoreResource,
        PipelineMetadataResource,
    )
    from src.metadata.repository import MetadataRepository

    database_url = _database_url()
    batch_id = f"20260808-jaeseong-{uuid.uuid4().hex[:8]}"
    data_root, _ = _accepted_fixture(tmp_path, batch_id)
    instance = dg.DagsterInstance.ephemeral()
    instance.add_dynamic_partitions(
        collection_batch_partitions.name,
        [batch_id],
    )
    resources = {
        "artifact_store": ArtifactStoreResource(
            data_root=str(data_root),
            contracts_dir=str(CONTRACTS_DIR),
        ),
        "pipeline_metadata": PipelineMetadataResource(
            database_url=database_url,
            data_root=str(data_root),
            contracts_dir=str(CONTRACTS_DIR),
            code_version="integration-test",
        ),
    }
    try:
        first = dg.materialize(
            [kurly_collection_submission, kurly_bronze_validated],
            instance=instance,
            partition_key=batch_id,
            resources=resources,
        )
        second = dg.materialize(
            [kurly_collection_submission, kurly_bronze_validated],
            instance=instance,
            partition_key=batch_id,
            resources=resources,
        )

        assert first.success
        assert second.success
        metadata = first.asset_materializations_for_node(
            "kurly_bronze_validated"
        )[0].metadata
        assert metadata["batch_id"].value == batch_id
        assert metadata["checksum"].value
        assert len(MetadataRepository(database_url).list_runs(batch_id=batch_id)) == 1
    finally:
        import psycopg

        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM pipeline_metadata.pipeline_runs WHERE batch_id = %s",
                (batch_id,),
            )


def test_repository_persists_run_step_artifact_quality_and_lineage() -> None:
    use_app("normalizer")
    import psycopg

    from src.metadata.migrations import apply_migrations
    from src.metadata.models import (
        ArtifactLineageCreate,
        PipelineArtifactCreate,
        PipelineRunCreate,
        PipelineStepCreate,
        QualityResultCreate,
        QualitySeverity,
        RunStatus,
        TriggerType,
    )
    from src.metadata.repository import MetadataConflictError, MetadataRepository

    database_url = _database_url()
    assert apply_migrations(database_url) in ([], ["0001"])
    assert apply_migrations(database_url) == []
    repository = MetadataRepository(database_url)
    token = uuid.uuid4().hex
    run_id = f"integration-run-{token}"
    parent_id = f"artifact-parent-{token}"
    child_id = f"artifact-child-{token}"
    try:
        created = repository.create_run(
            PipelineRunCreate(
                run_id=run_id,
                pipeline_name="metadata_integration",
                batch_id=f"batch-{token}",
                trigger_type=TriggerType.MANUAL,
                code_version="integration-test",
                config_hash="a" * 64,
            )
        )
        duplicate = repository.create_run(
            PipelineRunCreate(
                run_id=run_id,
                pipeline_name="metadata_integration",
                batch_id=f"batch-{token}",
                trigger_type=TriggerType.MANUAL,
                code_version="integration-test",
                config_hash="a" * 64,
            )
        )
        assert created["run_id"] == duplicate["run_id"]
        with pytest.raises(MetadataConflictError, match="code_version"):
            repository.create_run(
                PipelineRunCreate(
                    run_id=run_id,
                    pipeline_name="metadata_integration",
                    batch_id=f"batch-{token}",
                    trigger_type=TriggerType.MANUAL,
                    code_version="different-code",
                    config_hash="a" * 64,
                )
            )
        repository.transition_run(run_id, RunStatus.RUNNING)
        repository.create_step(
            PipelineStepCreate(run_id=run_id, step_key="transform")
        )
        repository.transition_step(
            run_id, "transform", 1, RunStatus.RUNNING, input_count=2
        )
        for artifact_id, logical_name, checksum in (
            (parent_id, "input", "b" * 64),
            (child_id, "output", "c" * 64),
        ):
            repository.register_artifact(
                PipelineArtifactCreate(
                    artifact_id=artifact_id,
                    run_id=run_id,
                    step_key="transform",
                    logical_name=logical_name,
                    path=f"/data/{logical_name}.parquet",
                    format="PARQUET",
                    schema_version="1.0.0",
                    checksum=checksum,
                    row_count=2,
                    byte_size=128,
                    code_version="integration-test",
                )
            )
        repository.add_lineage(
            ArtifactLineageCreate(
                parent_artifact_id=parent_id,
                child_artifact_id=child_id,
            )
        )
        with pytest.raises(ValueError, match="cycle rejected"):
            repository.add_lineage(
                ArtifactLineageCreate(
                    parent_artifact_id=child_id,
                    child_artifact_id=parent_id,
                )
            )
        repository.record_quality_result(
            QualityResultCreate(
                quality_result_id=f"quality-{token}",
                run_id=run_id,
                artifact_id=child_id,
                rule_id="fixture.non_empty",
                severity=QualitySeverity.ERROR,
                passed=True,
                observed_value="2",
                details={"fixture": True},
            )
        )
        repository.transition_step(
            run_id,
            "transform",
            1,
            RunStatus.SUCCEEDED,
            output_count=2,
        )
        repository.transition_run(run_id, RunStatus.SUCCEEDED)

        snapshot = repository.get_run(run_id)
        assert snapshot is not None
        assert snapshot["run"]["status"] == "SUCCEEDED"
        assert len(snapshot["steps"]) == 1
        assert len(snapshot["artifacts"]) == 2
        assert len(snapshot["quality_results"]) == 1
        assert repository.trace_ancestors(child_id)[0]["artifact_id"] == parent_id
        with psycopg.connect(database_url) as connection:
            columns = connection.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'pipeline_metadata'
                  AND table_name = 'pipeline_artifacts'
                """
            ).fetchall()
        assert "payload" not in {str(row[0]) for row in columns}
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM pipeline_metadata.pipeline_runs WHERE run_id = %s",
                (run_id,),
            )


def test_accepted_submission_adapter_is_idempotent(
    tmp_path: Path,
) -> None:
    use_app("normalizer")
    import psycopg

    from src.metadata.migrations import apply_migrations
    from src.metadata.repository import MetadataRepository
    from src.metadata.submission_adapter import register_accepted_submission

    database_url = _database_url()
    apply_migrations(database_url)
    batch_id = f"20260808-jaeseong-{uuid.uuid4().hex[:8]}"
    data_root, member = _accepted_fixture(tmp_path, batch_id)
    repository = MetadataRepository(database_url)
    run_id: str | None = None
    try:
        snapshot = register_accepted_submission(
            repository,
            data_root=data_root,
            batch_id=batch_id,
            member=member,
            code_version="integration-test",
            contracts_dir=CONTRACTS_DIR,
        )
        run_id = snapshot["run"]["run_id"]
        again = register_accepted_submission(
            repository,
            data_root=data_root,
            batch_id=batch_id,
            member=member,
            code_version="integration-test",
            contracts_dir=CONTRACTS_DIR,
        )
        assert again["run"]["run_id"] == run_id
        assert again["run"]["status"] == "SUCCEEDED"
        manifest = next(
            item
            for item in again["artifacts"]
            if item["logical_name"] == "collection_manifest"
        )
        ancestors = repository.trace_ancestors(manifest["artifact_id"])
        assert {item["logical_name"] for item in ancestors} >= {
            "products",
            "crawled_products",
            "discovered_products",
        }
    finally:
        if run_id is not None:
            with psycopg.connect(database_url) as connection:
                connection.execute(
                    "DELETE FROM pipeline_metadata.pipeline_runs WHERE run_id = %s",
                    (run_id,),
                )
