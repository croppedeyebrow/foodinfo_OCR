from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import use_app

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contracts"
CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"


@pytest.fixture()
def normalizer_src():
    root = use_app("normalizer")
    return root


def test_checksum_is_deterministic(normalizer_src) -> None:
    from src.checksum import compute_content_hash, with_content_hash

    payload = {
        "b": 2,
        "a": 1,
        "nested": {"z": 1, "a": [2, 1]},
        "content_hash": "should-be-ignored",
    }
    first = compute_content_hash(payload)
    second = compute_content_hash({"a": 1, "b": 2, "nested": {"a": [2, 1], "z": 1}})
    assert first == second
    sealed = with_content_hash(payload)
    assert sealed["content_hash"] == first
    assert len(first) == 64


def test_validate_valid_kurly_raw_after_seal(normalizer_src) -> None:
    from src.contracts import seal_payload, validate_payload

    raw = json.loads(
        (FIXTURES / "kurly_raw_product.valid.unsealed.json").read_text(encoding="utf-8")
    )
    sealed = seal_payload(raw)
    result = validate_payload(
        "kurly_raw_product",
        sealed,
        contracts_dir=CONTRACTS_DIR,
        check_checksum=True,
    )
    assert result.ok, result.issues


def test_validate_rejects_unsupported_major(normalizer_src) -> None:
    from src.contracts import validate_payload

    payload = json.loads(
        (FIXTURES / "kurly_raw_product.invalid_major.json").read_text(encoding="utf-8")
    )
    result = validate_payload(
        "kurly_raw_product",
        payload,
        contracts_dir=CONTRACTS_DIR,
        check_checksum=False,
    )
    assert not result.ok
    assert "UNSUPPORTED_SCHEMA_VERSION" in result.error_codes
    assert any(issue.path == "$.schema_version" for issue in result.issues)


def test_validate_rejects_missing_required(normalizer_src) -> None:
    from src.contracts import validate_payload

    payload = json.loads(
        (FIXTURES / "kurly_raw_product.invalid_missing.json").read_text(encoding="utf-8")
    )
    result = validate_payload(
        "kurly_raw_product",
        payload,
        contracts_dir=CONTRACTS_DIR,
        check_checksum=False,
    )
    assert not result.ok
    assert "SCHEMA_VALIDATION_FAILED" in result.error_codes


def test_checksum_mismatch_is_reported(normalizer_src) -> None:
    from src.contracts import seal_payload, validate_payload

    raw = json.loads(
        (FIXTURES / "kurly_raw_product.valid.unsealed.json").read_text(encoding="utf-8")
    )
    sealed = seal_payload(raw)
    sealed["content_hash"] = "0" * 64
    result = validate_payload(
        "kurly_raw_product",
        sealed,
        contracts_dir=CONTRACTS_DIR,
        check_checksum=True,
    )
    assert not result.ok
    assert "CHECKSUM_MISMATCH" in result.error_codes


def test_adapt_products_csv_roundtrip(normalizer_src, tmp_path: Path) -> None:
    from src.adapters.products_csv import adapt_products_csv, write_submission_json
    from src.contracts import validate_payload

    payload = adapt_products_csv(
        FIXTURES / "sample_products.csv",
        batch_id="20260808-jaeseong-001",
        member="jaeseong",
        run_id="adapt-run-001",
        status="DRAFT",
    )
    assert payload["row_count"] == 2
    assert payload["member"] == "jaeseong"
    assert payload["products"][0]["original_product_id"] == "1000001"
    # Legacy columns preserved on product rows
    assert payload["products"][0]["expiration_source"] == "DOM"

    out = tmp_path / "submission.json"
    write_submission_json(payload, out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    result = validate_payload(
        "collection_submission",
        loaded,
        contracts_dir=CONTRACTS_DIR,
        check_checksum=True,
    )
    assert result.ok, result.issues

    # Same input → same checksum
    again = adapt_products_csv(
        FIXTURES / "sample_products.csv",
        batch_id="20260808-jaeseong-001",
        member="jaeseong",
        run_id="adapt-run-001",
        status="DRAFT",
        created_at=__import__("datetime").datetime.fromisoformat(
            payload["created_at"]
        ),
    )
    assert again["content_hash"] == payload["content_hash"]


def test_ensure_storage_dirs(normalizer_src, tmp_path: Path) -> None:
    from src.storage_paths import ensure_storage_dirs, accepted_inbox_dir

    paths = ensure_storage_dirs(tmp_path)
    assert (tmp_path / "inbox" / "accepted").is_dir()
    assert (tmp_path / "silver").is_dir()
    assert (tmp_path / "gold").is_dir()
    assert (tmp_path / "quarantine").is_dir()
    assert accepted_inbox_dir(tmp_path, "b1") == tmp_path / "inbox" / "accepted" / "b1"
    assert len(paths) >= 8


def test_use_app_normalizer_resolves(normalizer_src) -> None:
    assert (normalizer_src / "src" / "cli.py").is_file()
