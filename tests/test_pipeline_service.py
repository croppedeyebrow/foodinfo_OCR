from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import use_app, use_console

BATCH_ID = "20260830-jaeseong-001"
MEMBER = "jaeseong"
CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contracts"


@pytest.fixture(autouse=True)
def _restore_console_path_after_normalizer_tests() -> None:
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


def test_fixture_stage_runs_end_to_end(normalizer_src: Path, tmp_path: Path) -> None:
    from src.normalizer_pipeline.service import PipelineService
    from src.normalizer_pipeline.store import InMemoryPipelineStore

    data_root, outcome_root = _accepted_batch(tmp_path)
    service = PipelineService.create(
        store=InMemoryPipelineStore(),
        data_root=data_root,
        outcome_root=outcome_root,
        code_version="test",
    )
    snapshot = service.start_run(
        batch_id=BATCH_ID,
        member=MEMBER,
        stage_key="fixture_echo",
    )
    assert snapshot["status"] == "PENDING"
    final = service.execute_run(snapshot["run_id"], member=MEMBER)
    assert final["status"] == "SUCCEEDED"
    assert final["progress"]["output_count"] == 1
    artifact_path = data_root / "pipeline" / "fixture" / BATCH_ID / "echo.json"
    assert artifact_path.is_file()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["batch_id"] == BATCH_ID


def test_duplicate_run_is_rejected(normalizer_src: Path, tmp_path: Path) -> None:
    from src.normalizer_pipeline.errors import DuplicateRunError
    from src.normalizer_pipeline.service import PipelineService
    from src.normalizer_pipeline.store import InMemoryPipelineStore

    data_root, outcome_root = _accepted_batch(tmp_path)
    service = PipelineService.create(
        store=InMemoryPipelineStore(),
        data_root=data_root,
        outcome_root=outcome_root,
        code_version="test",
    )
    first = service.start_run(
        batch_id=BATCH_ID,
        member=MEMBER,
        stage_key="fixture_echo",
    )
    with pytest.raises(DuplicateRunError):
        service.start_run(
            batch_id=BATCH_ID,
            member=MEMBER,
            stage_key="fixture_echo",
        )
    service.execute_run(first["run_id"], member=MEMBER)


def test_retry_after_failure_creates_new_attempt(
    normalizer_src: Path, tmp_path: Path
) -> None:
    from src.normalizer_pipeline.service import PipelineService
    from src.normalizer_pipeline.stages.fixture_echo import FixtureEchoStage
    from src.normalizer_pipeline.store import InMemoryPipelineStore

    data_root, outcome_root = _accepted_batch(tmp_path)

    class FailingStage(FixtureEchoStage):
        def execute(self, context):
            from src.normalizer_pipeline.stages.base import StageExecutionResult

            return StageExecutionResult(
                failed_count=1,
                error_code="FIXTURE_FAIL",
                error_message="intentional failure",
            )

    service = PipelineService.create(
        store=InMemoryPipelineStore(),
        data_root=data_root,
        outcome_root=outcome_root,
        code_version="test",
        stages={"fixture_echo": FailingStage()},
    )
    first = service.start_run(
        batch_id=BATCH_ID,
        member=MEMBER,
        stage_key="fixture_echo",
    )
    failed = service.execute_run(first["run_id"], member=MEMBER)
    assert failed["status"] == "FAILED"
    retry = service.retry_run(first["run_id"], member=MEMBER)
    assert retry["run_id"] != first["run_id"]
    assert retry["status"] == "PENDING"
