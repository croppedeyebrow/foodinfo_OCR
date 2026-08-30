from __future__ import annotations

import json
import shutil
from pathlib import Path

import polars as pl
import pytest

from conftest import use_app

BATCH_ID = "20260830-jaeseong-006"
MEMBER = "jaeseong"
CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contracts"


@pytest.fixture(autouse=True)
def _restore_console_path() -> None:
    from conftest import use_console

    yield
    use_console()


@pytest.fixture()
def normalizer_src() -> Path:
    return use_app("normalizer")


def _accepted_batch(tmp_path: Path) -> tuple[Path, Path]:
    from src.submission import submit_collection_batch

    data_root = tmp_path / "datasets"
    outcome_root = tmp_path / "outcome"
    discovery = data_root / "discovery" / BATCH_ID
    outcome = outcome_root / MEMBER / BATCH_ID
    discovery.mkdir(parents=True)
    outcome.mkdir(parents=True)
    (discovery / "discovered_products.csv").write_text(
        "original_product_id\n1000001\n", encoding="utf-8-sig"
    )
    (discovery / "crawled_products.csv").write_text(
        "original_product_id\n1000001\n", encoding="utf-8-sig"
    )
    (discovery / "image_text_check.csv").write_text(
        "image_path,text_presence\na.jpg,HAS_TEXT\n", encoding="utf-8-sig"
    )
    shutil.copy2(FIXTURES / "sample_products.csv", outcome / "products.csv")
    products = (outcome / "products.csv").read_text(encoding="utf-8-sig")
    products = products.replace("20260808-jaeseong-001", BATCH_ID)
    (outcome / "products.csv").write_text(products, encoding="utf-8-sig")
    submit_collection_batch(
        data_root=data_root,
        outcome_root=outcome_root,
        batch_id=BATCH_ID,
        member=MEMBER,
        contracts_dir=CONTRACTS_DIR,
        submitted_by="operator",
    )
    return data_root, outcome_root


def test_bronze_and_silver_pipeline(normalizer_src: Path, tmp_path: Path) -> None:
    from src.kurly_transform import run_kurly_bronze, run_kurly_silver
    from src.normalizer_pipeline.service import PipelineService
    from src.normalizer_pipeline.store import InMemoryPipelineStore
    from src.storage_paths import bronze_batch_dir, silver_batch_dir

    data_root, _ = _accepted_batch(tmp_path)
    bronze = run_kurly_bronze(
        data_root=data_root,
        batch_id=BATCH_ID,
        run_id=f"batch:{BATCH_ID}:kurly_bronze:1",
        code_version="test",
        attempt=1,
    )
    assert bronze.valid_count == 2
    assert bronze.quarantine_count == 0
    assert bronze.products_path.is_file()
    assert bronze.manifest_path.is_file()

    silver = run_kurly_silver(
        data_root=data_root,
        batch_id=BATCH_ID,
        run_id=f"batch:{BATCH_ID}:kurly_silver:1",
        code_version="test",
        attempt=1,
    )
    assert silver.unique_product_count == 2
    assert silver.evidence_path.is_file()
    assert silver.review_csv_path.is_file()
    assert silver.evidence_preservation_rate > 0

    service = PipelineService.create(
        store=InMemoryPipelineStore(),
        data_root=data_root,
        outcome_root=tmp_path / "outcome",
        code_version="test",
    )
    bronze_run = service.start_run(
        batch_id=BATCH_ID,
        member=MEMBER,
        stage_key="kurly_bronze",
    )
    bronze_final = service.execute_run(bronze_run["run_id"], member=MEMBER)
    assert bronze_final["status"] == "SUCCEEDED"

    silver_run = service.start_run(
        batch_id=BATCH_ID,
        member=MEMBER,
        stage_key="kurly_silver",
    )
    silver_final = service.execute_run(silver_run["run_id"], member=MEMBER)
    assert silver_final["status"] == "SUCCEEDED"
    assert (silver_batch_dir(data_root, "kurly", BATCH_ID) / "manifest.json").is_file()
    assert (bronze_batch_dir(data_root, "kurly", BATCH_ID) / "manifest.json").is_file()


def test_silver_deduplicates_duplicate_products(normalizer_src: Path, tmp_path: Path) -> None:
    from src.kurly_transform import run_kurly_bronze, run_kurly_silver
    from src.storage_paths import bronze_batch_dir

    data_root, _ = _accepted_batch(tmp_path)
    run_kurly_bronze(
        data_root=data_root,
        batch_id=BATCH_ID,
        run_id=f"batch:{BATCH_ID}:kurly_bronze:1",
        code_version="test",
        attempt=1,
    )
    bronze_path = bronze_batch_dir(data_root, "kurly", BATCH_ID) / "products.parquet"
    frame = pl.read_parquet(bronze_path)
    first = frame.head(1)
    duplicated = pl.concat([first] * 55 + [frame], how="vertical_relaxed")
    duplicated.write_parquet(bronze_path)

    silver = run_kurly_silver(
        data_root=data_root,
        batch_id=BATCH_ID,
        run_id=f"batch:{BATCH_ID}:kurly_silver:1",
        code_version="test",
        attempt=1,
    )
    assert silver.input_count == 57
    assert silver.unique_product_count == 2

    evidence_lines = (
        silver.evidence_path.read_text(encoding="utf-8").strip().splitlines()
    )
    evidence = [json.loads(line) for line in evidence_lines]
    duplicated_evidence = next(
        item for item in evidence if item["original_product_id"] == "1000001"
    )
    assert duplicated_evidence["duplicate_count"] == 56


def test_bronze_is_deterministic(normalizer_src: Path, tmp_path: Path) -> None:
    from src.kurly_transform import run_kurly_bronze

    data_root, _ = _accepted_batch(tmp_path)
    run_id = f"batch:{BATCH_ID}:kurly_bronze:deterministic"
    first = run_kurly_bronze(
        data_root=data_root,
        batch_id=BATCH_ID,
        run_id=run_id,
        code_version="test",
        attempt=1,
    )
    first_checksum = json.loads(first.manifest_path.read_text(encoding="utf-8"))[
        "products_checksum"
    ]
    shutil.rmtree(first.batch_dir)
    second = run_kurly_bronze(
        data_root=data_root,
        batch_id=BATCH_ID,
        run_id=run_id,
        code_version="test",
        attempt=2,
    )
    second_checksum = json.loads(second.manifest_path.read_text(encoding="utf-8"))[
        "products_checksum"
    ]
    assert first_checksum == second_checksum


def test_silver_failure_does_not_remove_existing_success(
    normalizer_src: Path, tmp_path: Path
) -> None:
    from src.kurly_transform import run_kurly_bronze, run_kurly_silver
    from src.storage_paths import bronze_batch_dir, silver_batch_dir

    data_root, _ = _accepted_batch(tmp_path)
    run_kurly_bronze(
        data_root=data_root,
        batch_id=BATCH_ID,
        run_id=f"batch:{BATCH_ID}:kurly_bronze:1",
        code_version="test",
        attempt=1,
    )
    run_kurly_silver(
        data_root=data_root,
        batch_id=BATCH_ID,
        run_id=f"batch:{BATCH_ID}:kurly_silver:1",
        code_version="test",
        attempt=1,
    )
    silver_dir = silver_batch_dir(data_root, "kurly", BATCH_ID)
    original_checksum = json.loads(
        (silver_dir / "manifest.json").read_text(encoding="utf-8")
    )["products_checksum"]

    bronze_dir = bronze_batch_dir(data_root, "kurly", BATCH_ID)
    hidden = bronze_dir.with_name(f".hidden-{BATCH_ID}")
    bronze_dir.replace(hidden)
    with pytest.raises(FileNotFoundError):
        run_kurly_silver(
            data_root=data_root,
            batch_id=BATCH_ID,
            run_id=f"batch:{BATCH_ID}:kurly_silver:2",
            code_version="test",
            attempt=2,
        )
    hidden.replace(bronze_dir)

    preserved = json.loads(
        (silver_dir / "manifest.json").read_text(encoding="utf-8")
    )["products_checksum"]
    assert preserved == original_checksum


def test_text_helpers(normalizer_src: Path) -> None:
    from src.kurly_transform.text import clean_text, normalize_storage_type, parse_expiration

    assert clean_text("<b>사과</b>") == "사과"
    storage, review = normalize_storage_type(
        storage_type_dom="REFRIGERATED",
        storage_method_dom="냉장 보관",
    )
    assert storage == "REFRIGERATED"
    assert review is False
    parsed = parse_expiration("제조일로부터 7일")
    assert parsed.value == 7.0
    assert parsed.unit == "DAY"
    assert parsed.basis == "MANUFACTURE"
