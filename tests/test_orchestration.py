from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from conftest import use_app

dg = pytest.importorskip("dagster")

from orchestration.artifact import ArtifactReference
from orchestration.assets import (
    FUTURE_ASSET_SPECS,
    kurly_bronze_validated,
    kurly_collection_submission,
)
from orchestration.jobs import ALL_JOBS, publish_gold_dataset
from orchestration.partitions import collection_batch_partitions
from orchestration.resources import (
    ArtifactStoreResource,
    DuckDBResource,
    PipelineMetadataResource,
)
from orchestration.sensors import accepted_collection_sensor

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contracts"
CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"


def _accepted_fixture(tmp_path: Path, batch_id: str) -> tuple[Path, str]:
    use_app("normalizer")
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
    (outcome / "products.csv").write_text(
        products.replace("20260808-jaeseong-001", batch_id),
        encoding="utf-8-sig",
    )
    submit_collection_batch(
        data_root=data_root,
        outcome_root=outcome_root,
        batch_id=batch_id,
        member=member,
        contracts_dir=CONTRACTS_DIR,
    )
    return data_root, member


def test_artifact_store_returns_reference_not_payload(tmp_path: Path) -> None:
    batch_id = f"20260808-jaeseong-{uuid.uuid4().hex[:8]}"
    data_root, _ = _accepted_fixture(tmp_path, batch_id)
    resource = ArtifactStoreResource(
        data_root=str(data_root),
        contracts_dir=str(CONTRACTS_DIR),
    )

    reference = resource.collection_submission_reference(batch_id=batch_id)

    assert isinstance(reference, ArtifactReference)
    assert reference.batch_id == batch_id
    assert reference.path.endswith("/manifest.json")
    assert reference.checksum
    assert resource.accepted_batch_ids() == [batch_id]


def test_duckdb_resource_uses_temp_database(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse" / "pipeline.duckdb"
    resource = DuckDBResource(database_path=str(database_path))

    with resource.connect() as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)

    assert database_path.is_file()


def test_full_asset_graph_and_operator_job_names_are_declared() -> None:
    from orchestration.definitions import defs

    dg.Definitions.validate_loadable(defs)
    future_keys = {spec.key.to_user_string() for spec in FUTURE_ASSET_SPECS}
    assert future_keys == {
        "kurly_silver_freshness",
        "mfds_source_pdf",
        "mfds_bronze_records",
        "mfds_silver_freshness",
        "reconciled_freshness",
        "freshness_quality_checked",
        "gold_freshness_profiles",
        "backend_export_bundle",
    }
    assert {job.name for job in ALL_JOBS} == {
        "process_collection_batch",
        "refresh_mfds_reference",
        "rebuild_reconciliation",
        "publish_gold_dataset",
    }


def test_future_job_fails_instead_of_fabricating_output() -> None:
    result = publish_gold_dataset.execute_in_process(raise_on_error=False)

    assert not result.success


def test_sensor_requests_new_batch_partition(tmp_path: Path) -> None:
    batch_id = f"20260808-jaeseong-{uuid.uuid4().hex[:8]}"
    data_root, _ = _accepted_fixture(tmp_path, batch_id)
    instance = dg.DagsterInstance.ephemeral()
    context = dg.build_sensor_context(
        instance=instance,
        resources={
            "artifact_store": ArtifactStoreResource(
                data_root=str(data_root),
                contracts_dir=str(CONTRACTS_DIR),
            )
        },
    )

    result = accepted_collection_sensor(context)

    assert [request.partition_key for request in result.run_requests] == [batch_id]
    assert len(result.dynamic_partitions_requests) == 1


def test_upstream_validation_failure_skips_downstream(tmp_path: Path) -> None:
    use_app("normalizer")
    batch_id = "20260808-jaeseong-missing"
    instance = dg.DagsterInstance.ephemeral()
    instance.add_dynamic_partitions(
        collection_batch_partitions.name,
        [batch_id],
    )
    result = dg.materialize(
        [kurly_collection_submission, kurly_bronze_validated],
        instance=instance,
        partition_key=batch_id,
        resources={
            "artifact_store": ArtifactStoreResource(
                data_root=str(tmp_path / "datasets"),
                contracts_dir=str(CONTRACTS_DIR),
            ),
            "pipeline_metadata": PipelineMetadataResource(
                database_url="postgresql://unused",
                data_root=str(tmp_path / "datasets"),
                contracts_dir=str(CONTRACTS_DIR),
            ),
        },
        raise_on_error=False,
    )

    assert not result.success
    assert not result.asset_materializations_for_node(
        "kurly_bronze_validated"
    )
