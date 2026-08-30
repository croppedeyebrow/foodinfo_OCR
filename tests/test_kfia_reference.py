from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from conftest import use_app

DATASET_VERSION = "KFIA-2026-08"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "kfia"
NATIVE_SAMPLE = FIXTURES / "shelf_life_output.native.sample.csv"


@pytest.fixture(autouse=True)
def _restore_console_path() -> None:
    from conftest import use_console

    yield
    use_console()


@pytest.fixture()
def normalizer_src() -> Path:
    return use_app("normalizer")


def _register_fixture(data_root: Path) -> Path:
    from src.reference_registration import register_reference_export

    result = register_reference_export(
        data_root=data_root,
        dataset_version=DATASET_VERSION,
        export_path=NATIVE_SAMPLE,
        registered_by="operator",
    )
    assert not result.duplicate
    return result.manifest_path


def test_kfia_native_bronze_and_silver_pipeline(normalizer_src: Path, tmp_path: Path) -> None:
    from src.kfia_transform import run_kfia_bronze, run_kfia_silver
    from src.reference_registration import mark_reference_validated
    from src.storage_paths import bronze_batch_dir, silver_batch_dir

    data_root = tmp_path / "datasets"
    _register_fixture(data_root)
    mark_reference_validated(data_root, DATASET_VERSION)

    bronze = run_kfia_bronze(
        data_root=data_root,
        dataset_version=DATASET_VERSION,
        run_id=f"batch:{DATASET_VERSION}:kfia_reference_bronze:1",
        code_version="test",
        attempt=1,
    )
    assert bronze.input_count == 3
    assert bronze.valid_count == 3
    assert bronze.quarantine_count == 0

    silver = run_kfia_silver(
        data_root=data_root,
        dataset_version=DATASET_VERSION,
        run_id=f"batch:{DATASET_VERSION}:kfia_reference_silver:1",
        code_version="test",
        attempt=1,
    )
    assert silver.record_count == 3
    assert silver.review_required_count >= 2
    assert silver.approved_count >= 1

    from src.normalizer_pipeline.service import PipelineService
    from src.normalizer_pipeline.store import InMemoryPipelineStore

    service = PipelineService.create(
        store=InMemoryPipelineStore(),
        data_root=data_root,
        outcome_root=tmp_path / "outcome",
        code_version="test",
    )
    snapshot = service.start_run(
        batch_id=DATASET_VERSION,
        member="operator",
        stage_key="kfia_reference_silver",
    )
    final = service.execute_run(snapshot["run_id"], member="operator")
    assert final["status"] == "SUCCEEDED"
    assert final["progress"]["output_count"] == 3

    silver_frame = pl.read_parquet(silver.records_path)
    assert set(silver_frame["source"].to_list()) == {"KFIA"}
    assert silver_frame["food_name"].null_count() == 3

    bronze_manifest = json.loads(
        (bronze_batch_dir(data_root, "kfia", DATASET_VERSION) / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    silver_manifest = json.loads(
        (silver_batch_dir(data_root, "kfia", DATASET_VERSION) / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert bronze_manifest["valid_count"] == 3
    assert silver_manifest["record_count"] == 3


def test_kfia_bronze_quarantines_invalid_rows(normalizer_src: Path, tmp_path: Path) -> None:
    from src.kfia_transform import run_kfia_bronze
    from src.reference_registration import register_reference_export

    data_root = tmp_path / "datasets"
    export_path = tmp_path / "invalid.csv"
    export_path.write_text(
        "품목코드,식품유형,소비기한참고값_일,단위,온도별_상세_json,source_pdf,source_page,추출일시\n"
        ",테스트,10,일,[],1. 테스트.pdf,1,2026-07-03 21:54:05\n"
        "A001,정상,10,일,[],1. 테스트.pdf,2,2026-07-03 21:54:05\n",
        encoding="utf-8",
    )
    register_reference_export(
        data_root=data_root,
        dataset_version=DATASET_VERSION,
        export_path=export_path,
        registered_by="operator",
    )
    bronze = run_kfia_bronze(
        data_root=data_root,
        dataset_version=DATASET_VERSION,
        run_id="run-invalid",
        code_version="test",
        attempt=1,
    )
    assert bronze.valid_count == 1
    assert bronze.quarantine_count == 1
