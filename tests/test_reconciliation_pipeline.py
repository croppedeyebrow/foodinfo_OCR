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
    from src.kurly_transform.common import atomic_write_parquet, now_iso, parquet_checksum
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
            "source_record_id": "p1",
            "content_hash": "a" * 64,
            "parser_version": "test",
            "created_at": now_iso(),
            "food_name_normalized": "소시지",
            "storage_type": "ROOM",
            "expiration_value": 180.0,
            "expiration_unit": "DAY",
            "expiration_text_raw": "180일",
        },
        {
            "schema_version": "1.0.0",
            "run_id": "test",
            "batch_id": KURLY_BATCH,
            "record_id": "kurly-unknown",
            "source": "KURLY",
            "source_record_id": "p2",
            "content_hash": "b" * 64,
            "parser_version": "test",
            "created_at": now_iso(),
            "food_name_normalized": "없는식품",
            "storage_type": "ROOM",
            "expiration_value": 10.0,
            "expiration_unit": "DAY",
            "expiration_text_raw": "10일",
        },
    ]
    products_path = batch_dir / "products.parquet"
    atomic_write_parquet(products_path, pl.DataFrame(records))
    manifest = {
        "schema_version": "1.0.0",
        "unique_product_count": 2,
        "products_checksum": parquet_checksum(products_path),
        "code_version": "test",
    }
    (batch_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )


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
        "schema_version": "1.0.0",
        "record_count": 1,
        "records_checksum": parquet_checksum(records_path),
        "code_version": "test",
    }
    (batch_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )


def test_kurly_kfia_reconcile_pipeline(normalizer_src: Path, tmp_path: Path) -> None:
    from src.normalizer_pipeline.service import PipelineService
    from src.normalizer_pipeline.store import InMemoryPipelineStore
    from src.reconciliation import run_kurly_kfia_reconcile
    from src.storage_paths import reconciled_pair_dir

    data_root = tmp_path / "datasets"
    _write_kurly_silver(data_root)
    _write_kfia_silver(data_root)

    result = run_kurly_kfia_reconcile(
        data_root=data_root,
        pair_id=PAIR_ID,
        run_id=f"batch:{PAIR_ID}:kurly_kfia_reconcile:1",
        code_version="test",
        attempt=1,
    )
    assert result.input_count == 2
    assert result.approved_count == 1
    assert result.review_required_count == 1
    assert result.no_reference_count == 1
    assert result.manifest_path.is_file()
    assert result.review_csv_path.is_file()

    frame = pl.read_parquet(result.records_path)
    assert frame.height == 2
    assert set(frame["review_status"].to_list()) == {"APPROVED", "REVIEW_REQUIRED"}

    service = PipelineService.create(
        store=InMemoryPipelineStore(),
        data_root=data_root,
        outcome_root=tmp_path / "outcome",
        code_version="test",
    )
    snapshot = service.start_run(
        batch_id=PAIR_ID,
        member="operator",
        stage_key="kurly_kfia_reconcile",
    )
    final = service.execute_run(snapshot["run_id"], member="operator")
    assert final["status"] == "SUCCEEDED"
    assert final["progress"]["output_count"] == 2

    manifest = json.loads(
        (reconciled_pair_dir(data_root, PAIR_ID) / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["approved_count"] == 1
    assert manifest["no_reference_count"] == 1


def test_append_review_decision(normalizer_src: Path, tmp_path: Path) -> None:
    from src.reconciliation import append_review_decision, run_kurly_kfia_reconcile

    data_root = tmp_path / "datasets"
    _write_kurly_silver(data_root)
    _write_kfia_silver(data_root)
    result = run_kurly_kfia_reconcile(
        data_root=data_root,
        pair_id=PAIR_ID,
        run_id=f"batch:{PAIR_ID}:kurly_kfia_reconcile:1",
        code_version="test",
        attempt=1,
    )
    review_frame = pl.read_csv(result.review_csv_path)
    reconciled_record_id = str(review_frame["reconciled_record_id"][0])

    decision = {
        "schema_version": "1.0.0",
        "decision_id": str(uuid.uuid4()),
        "reconcile_pair_id": PAIR_ID,
        "reconciled_record_id": reconciled_record_id,
        "kurly_batch_id": KURLY_BATCH,
        "kfia_dataset_version": KFIA_DATASET,
        "reviewer": "operator",
        "decided_at": "2026-08-30T12:00:00+09:00",
        "action": "APPROVE",
        "reason": "manual confirmation",
        "selected_kfia_record_id": None,
        "rule_version": "kurly_kfia_reconcile_v1.0.0",
    }
    path = append_review_decision(
        data_root=data_root,
        pair_id=PAIR_ID,
        decision=decision,
    )
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["action"] == "APPROVE"
