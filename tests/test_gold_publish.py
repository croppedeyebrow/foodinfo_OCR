from __future__ import annotations

import json
import uuid
from pathlib import Path

import polars as pl
import pytest

from conftest import use_app

KURLY_BATCH = "20260830-jaeseong-001"
KFIA_DATASET = "KFIA-2026-08"
PAIR_ID = f"{KURLY_BATCH}__{KFIA_DATASET}"


@pytest.fixture(autouse=True)
def _restore_console_path() -> None:
    from conftest import use_console

    yield
    use_console()


@pytest.fixture()
def normalizer_src() -> Path:
    return use_app("normalizer")


def _write_kurly_silver(data_root: Path) -> None:
    from src.kurly_transform.common import atomic_write_jsonl, atomic_write_parquet, now_iso, parquet_checksum
    from src.storage_paths import silver_batch_dir

    batch_dir = silver_batch_dir(data_root, "kurly", KURLY_BATCH)
    batch_dir.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "schema_version": "1.0.0",
            "run_id": "test",
            "batch_id": KURLY_BATCH,
            "record_id": "kurly-sausage",
            "source": "KURLY",
            "source_record_id": "bronze-sausage",
            "content_hash": "a" * 64,
            "parser_version": "test",
            "created_at": now_iso(),
            "food_name_normalized": "소시지",
            "storage_type": "ROOM",
            "expiration_value": 180.0,
            "expiration_unit": "DAY",
            "expiration_basis": "MANUFACTURE",
            "expiration_text_raw": "180일",
        }
    ]
    products_path = batch_dir / "products.parquet"
    atomic_write_parquet(products_path, pl.DataFrame(records))
    evidence = [
        {
            "original_product_id": "10001",
            "selected_record_id": "bronze-sausage",
            "review_status": "OK",
        }
    ]
    atomic_write_jsonl(batch_dir / "evidence.jsonl", evidence)
    manifest = {
        "unique_product_count": 1,
        "products_checksum": parquet_checksum(products_path),
        "code_version": "test",
    }
    (batch_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _write_kfia_silver(data_root: Path) -> None:
    from src.kurly_transform.common import atomic_write_parquet, now_iso, parquet_checksum
    from src.storage_paths import silver_batch_dir

    batch_dir = silver_batch_dir(data_root, "kfia", KFIA_DATASET)
    batch_dir.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "schema_version": "1.0.0",
            "run_id": "test",
            "batch_id": KFIA_DATASET,
            "record_id": "kfia-sausage",
            "source": "KFIA",
            "source_record_id": "17-1-1-1",
            "content_hash": "c" * 64,
            "parser_version": "test",
            "created_at": now_iso(),
            "reference_item_code": "17-1-1-1",
            "food_type": "소시지",
            "food_name": None,
            "storage_type": "AMBIENT",
            "reference_shelf_life_days": 180.0,
            "original_unit": "일",
            "review_status": "APPROVED",
        }
    ]
    records_path = batch_dir / "records.parquet"
    atomic_write_parquet(records_path, pl.DataFrame(records))
    manifest = {
        "record_count": 1,
        "records_checksum": parquet_checksum(records_path),
        "code_version": "test",
    }
    (batch_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _write_reconciled(data_root: Path) -> None:
    from src.checksum import with_content_hash
    from src.kurly_transform.common import atomic_write_parquet, now_iso, parquet_checksum
    from src.storage_paths import reconciled_pair_dir

    batch_dir = reconciled_pair_dir(data_root, PAIR_ID)
    batch_dir.mkdir(parents=True, exist_ok=True)
    reconciled = with_content_hash(
        {
            "schema_version": "1.0.0",
            "run_id": "test",
            "batch_id": PAIR_ID,
            "record_id": str(uuid.uuid4()),
            "source": "RECONCILER",
            "source_record_id": "kurly-sausage",
            "parser_version": "test",
            "created_at": now_iso(),
            "kurly_record_id": "kurly-sausage",
            "mfds_record_id": "kfia-sausage",
            "review_status": "APPROVED",
            "match_type": "EXACT_NAME_UNIQUE",
            "confidence": 1.0,
            "rule_id": "RECONCILE-002",
            "rule_version": "kurly_kfia_reconcile_v1.0.0",
            "selected_source": "KURLY",
            "selected_storage_type": "ROOM",
            "selected_expiration_text": "180일",
        }
    )
    records_path = batch_dir / "records.parquet"
    atomic_write_parquet(records_path, pl.DataFrame([reconciled]))
    manifest = {
        "record_count": 1,
        "input_count": 1,
        "approved_count": 1,
        "review_required_count": 0,
        "records_checksum": parquet_checksum(records_path),
        "code_version": "test",
        "rule_version": "kurly_kfia_reconcile_v1.0.0",
    }
    (batch_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_gold_publish_from_approved_reconciled(normalizer_src: Path, tmp_path: Path) -> None:
    from src.gold_transform import (
        GoldDatasetVersionExistsError,
        build_results_summary,
        load_lineage_for_gold_record,
        run_gold_freshness_publish,
    )
    from src.storage_paths import gold_freshness_profiles_dir

    data_root = tmp_path / "datasets"
    _write_kurly_silver(data_root)
    _write_kfia_silver(data_root)
    _write_reconciled(data_root)

    result = run_gold_freshness_publish(
        data_root=data_root,
        pair_id=PAIR_ID,
        run_id=f"batch:{PAIR_ID}:gold_freshness_publish:1",
        code_version="test",
        attempt=1,
    )
    assert result.record_count == 1
    assert result.lineage_linked_count == 1
    assert result.manifest_path.is_file()
    assert result.csv_path.is_file()
    assert result.quality_summary_path.is_file()

    frame = pl.read_parquet(result.records_path)
    assert frame.height == 1
    assert frame["review_status"][0] == "APPROVED"
    assert frame["external_product_id"][0] == "10001"
    assert frame["food_mapping_key"][0] == "17-1-1-1"

    gold_record_id = str(frame["record_id"][0])
    lineage = load_lineage_for_gold_record(data_root, PAIR_ID, gold_record_id)
    assert lineage is not None
    assert lineage["lineage_complete"] is True
    assert any(step["layer"] == "gold" for step in lineage["chain"])

    summary = build_results_summary(data_root, PAIR_ID)
    assert summary["has_gold"] is True
    assert summary["layer_counts"]["gold"] == 1

    with pytest.raises(GoldDatasetVersionExistsError):
        run_gold_freshness_publish(
            data_root=data_root,
            pair_id=PAIR_ID,
            run_id=f"batch:{PAIR_ID}:gold_freshness_publish:2",
            code_version="test",
            attempt=2,
        )

    assert gold_freshness_profiles_dir(data_root, PAIR_ID).is_dir()


def test_gold_publish_stage_end_to_end(normalizer_src: Path, tmp_path: Path) -> None:
    from src.normalizer_pipeline.service import PipelineService
    from src.normalizer_pipeline.store import InMemoryPipelineStore

    data_root = tmp_path / "datasets"
    _write_kurly_silver(data_root)
    _write_kfia_silver(data_root)
    _write_reconciled(data_root)

    service = PipelineService.create(
        store=InMemoryPipelineStore(),
        data_root=data_root,
        outcome_root=tmp_path / "outcome",
        code_version="test",
    )
    snapshot = service.start_run(
        batch_id=PAIR_ID,
        member="operator",
        stage_key="gold_freshness_publish",
    )
    final = service.execute_run(snapshot["run_id"], member="operator")
    assert final["status"] == "SUCCEEDED"
    assert final["progress"]["output_count"] == 1
