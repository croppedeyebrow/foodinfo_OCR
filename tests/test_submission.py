from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import use_app

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contracts"
CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"
BATCH_ID = "20260808-jaeseong-001"
MEMBER = "jaeseong"


@pytest.fixture()
def normalizer_src() -> Path:
    return use_app("normalizer")


def _batch_fixture(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "datasets"
    outcome_root = tmp_path / "outcome"
    discovery = data_root / "discovery" / BATCH_ID
    outcome = outcome_root / MEMBER / BATCH_ID
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
    shutil.copy2(FIXTURES / "sample_products.csv", outcome / "products.csv")
    return data_root, outcome_root


def test_rejects_path_traversal_and_member_mismatch(normalizer_src: Path) -> None:
    from src.submission import SubmissionError, validate_batch_identity

    with pytest.raises(SubmissionError, match="batch_id"):
        validate_batch_identity("../escape", MEMBER)
    with pytest.raises(SubmissionError, match="소유"):
        validate_batch_identity(BATCH_ID, "sunyeong")


def test_local_validation_writes_ready_report(
    normalizer_src: Path, tmp_path: Path
) -> None:
    from src.submission import validate_and_write_report

    data_root, outcome_root = _batch_fixture(tmp_path)
    report = validate_and_write_report(
        data_root=data_root,
        outcome_root=outcome_root,
        batch_id=BATCH_ID,
        member=MEMBER,
        contracts_dir=CONTRACTS_DIR,
    )
    assert report.status == "READY"
    assert report.checksum_status == "VALID"
    assert report.counts["products"] == 2
    assert report.parser_versions == ["0.2.0"]
    assert report.batch_sha256 is not None
    saved = json.loads(
        (outcome_root / MEMBER / BATCH_ID / "validation_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved["status"] == "READY"


def test_missing_required_file_is_rejected(
    normalizer_src: Path, tmp_path: Path
) -> None:
    from src.submission import validate_and_write_report

    data_root, outcome_root = _batch_fixture(tmp_path)
    (data_root / "discovery" / BATCH_ID / "image_text_check.csv").unlink()
    report = validate_and_write_report(
        data_root=data_root,
        outcome_root=outcome_root,
        batch_id=BATCH_ID,
        member=MEMBER,
        contracts_dir=CONTRACTS_DIR,
    )
    assert report.status == "REJECTED"
    assert any(
        issue["error_code"] == "REQUIRED_FILE_MISSING"
        for issue in report.errors
    )


def test_submit_is_atomic_and_preserves_sources(
    normalizer_src: Path, tmp_path: Path
) -> None:
    from src.contracts import validate_payload
    from src.submission import file_sha256, submit_collection_batch

    data_root, outcome_root = _batch_fixture(tmp_path)
    source = outcome_root / MEMBER / BATCH_ID / "products.csv"
    before = file_sha256(source)
    report = submit_collection_batch(
        data_root=data_root,
        outcome_root=outcome_root,
        batch_id=BATCH_ID,
        member=MEMBER,
        contracts_dir=CONTRACTS_DIR,
    )
    accepted = data_root / "inbox" / "accepted" / BATCH_ID
    assert report.status == "ACCEPTED"
    assert before == file_sha256(source)
    assert before == file_sha256(accepted / "outcome" / "products.csv")
    assert not list((data_root / "inbox" / "accepted").glob(".*.tmp"))

    manifest = json.loads((accepted / "manifest.json").read_text(encoding="utf-8"))
    result = validate_payload(
        "collection_submission",
        manifest,
        contracts_dir=CONTRACTS_DIR,
        check_checksum=True,
    )
    assert result.ok, result.issues
    assert manifest["status"] == "ACCEPTED"


def test_duplicate_submission_is_idempotent(
    normalizer_src: Path, tmp_path: Path
) -> None:
    from src.submission import submit_collection_batch

    data_root, outcome_root = _batch_fixture(tmp_path)
    first = submit_collection_batch(
        data_root=data_root,
        outcome_root=outcome_root,
        batch_id=BATCH_ID,
        member=MEMBER,
        contracts_dir=CONTRACTS_DIR,
    )
    second = submit_collection_batch(
        data_root=data_root,
        outcome_root=outcome_root,
        batch_id=BATCH_ID,
        member=MEMBER,
        contracts_dir=CONTRACTS_DIR,
    )
    assert first.status == second.status == "ACCEPTED"
    assert second.duplicate is True
    assert first.submission_content_hash == second.submission_content_hash


def test_different_content_cannot_replace_accepted_batch(
    normalizer_src: Path, tmp_path: Path
) -> None:
    from src.submission import SubmissionError, file_sha256, submit_collection_batch

    data_root, outcome_root = _batch_fixture(tmp_path)
    submit_collection_batch(
        data_root=data_root,
        outcome_root=outcome_root,
        batch_id=BATCH_ID,
        member=MEMBER,
        contracts_dir=CONTRACTS_DIR,
    )
    accepted_products = (
        data_root / "inbox" / "accepted" / BATCH_ID / "outcome" / "products.csv"
    )
    accepted_hash = file_sha256(accepted_products)
    source = outcome_root / MEMBER / BATCH_ID / "products.csv"
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    source.write_text("\n".join([*lines, lines[-1]]) + "\n", encoding="utf-8-sig")

    with pytest.raises(
        SubmissionError, match="다른 내용의 accepted batch"
    ):
        submit_collection_batch(
            data_root=data_root,
            outcome_root=outcome_root,
            batch_id=BATCH_ID,
            member=MEMBER,
            contracts_dir=CONTRACTS_DIR,
        )
    assert file_sha256(accepted_products) == accepted_hash


def test_tampered_accepted_manifest_checksum_is_rejected(
    normalizer_src: Path, tmp_path: Path
) -> None:
    from src.submission import SubmissionError, submit_collection_batch

    data_root, outcome_root = _batch_fixture(tmp_path)
    submit_collection_batch(
        data_root=data_root,
        outcome_root=outcome_root,
        batch_id=BATCH_ID,
        member=MEMBER,
        contracts_dir=CONTRACTS_DIR,
    )
    manifest_path = (
        data_root / "inbox" / "accepted" / BATCH_ID / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["content_hash"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SubmissionError, match="content_hash"):
        submit_collection_batch(
            data_root=data_root,
            outcome_root=outcome_root,
            batch_id=BATCH_ID,
            member=MEMBER,
            contracts_dir=CONTRACTS_DIR,
        )


def test_copy_failure_cleans_temp_and_preserves_source(
    normalizer_src: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.submission import file_sha256, submit_collection_batch

    data_root, outcome_root = _batch_fixture(tmp_path)
    source = outcome_root / MEMBER / BATCH_ID / "products.csv"
    before = file_sha256(source)

    def fail_copytree(*args, **kwargs):
        raise OSError("simulated copy failure")

    monkeypatch.setattr("src.submission.shutil.copytree", fail_copytree)
    with pytest.raises(OSError, match="simulated"):
        submit_collection_batch(
            data_root=data_root,
            outcome_root=outcome_root,
            batch_id=BATCH_ID,
            member=MEMBER,
            contracts_dir=CONTRACTS_DIR,
        )

    accepted_root = data_root / "inbox" / "accepted"
    assert not (accepted_root / BATCH_ID).exists()
    assert not list(accepted_root.glob(".*.tmp"))
    assert file_sha256(source) == before
