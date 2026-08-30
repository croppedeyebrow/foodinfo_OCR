from __future__ import annotations

from pathlib import Path

import pytest

from conftest import use_app


@pytest.fixture(autouse=True)
def _restore_console_path() -> None:
    from conftest import use_console

    yield
    use_console()


@pytest.fixture()
def normalizer_src() -> Path:
    return use_app("normalizer")


def _kurly_row(**overrides: object) -> dict:
    base = {
        "record_id": "kurly-1",
        "food_name_normalized": "소시지",
        "storage_type": "ROOM",
        "expiration_value": 180.0,
        "expiration_unit": "DAY",
        "expiration_text_raw": "제조일로부터 180일",
    }
    base.update(overrides)
    return base


def _kfia_row(**overrides: object) -> dict:
    base = {
        "record_id": "kfia-1",
        "reference_item_code": "17-1-1-1",
        "food_type": "소시지",
        "storage_type": "AMBIENT",
        "reference_shelf_life_days": 180.0,
        "original_unit": "일",
    }
    base.update(overrides)
    return base


def test_storage_types_compatible_room_and_ambient(normalizer_src: Path) -> None:
    from src.reconciliation.matching import storage_types_compatible

    assert storage_types_compatible("ROOM", "AMBIENT")
    assert storage_types_compatible("REFRIGERATED", "REFRIGERATED")
    assert not storage_types_compatible("REFRIGERATED", "AMBIENT")


def test_exact_name_unique_with_aligned_expiration_is_approved(normalizer_src: Path) -> None:
    from src.reconciliation.matching import match_kurly_record

    outcome = match_kurly_record(
        _kurly_row(),
        kfia_rows=[_kfia_row()],
        managed_mappings={},
    )
    assert outcome.review_status == "APPROVED"
    assert outcome.match_type == "EXACT_NAME_UNIQUE"
    assert outcome.rule_id == "RECONCILE-002"
    assert outcome.mfds_record_id == "kfia-1"


def test_exact_name_expiration_mismatch_requires_review(normalizer_src: Path) -> None:
    from src.reconciliation.matching import match_kurly_record

    outcome = match_kurly_record(
        _kurly_row(expiration_value=90.0),
        kfia_rows=[_kfia_row()],
        managed_mappings={},
    )
    assert outcome.review_status == "REVIEW_REQUIRED"
    assert outcome.match_type == "EXACT_NAME_EXPIRATION_MISMATCH"
    assert outcome.rule_id == "RECONCILE-004"


def test_no_reference_when_food_type_missing(normalizer_src: Path) -> None:
    from src.reconciliation.matching import match_kurly_record

    outcome = match_kurly_record(
        _kurly_row(food_name_normalized="없는식품"),
        kfia_rows=[_kfia_row()],
        managed_mappings={},
    )
    assert outcome.review_status == "REVIEW_REQUIRED"
    assert outcome.match_type == "NO_REFERENCE"
    assert outcome.rule_id == "RECONCILE-005"


def test_managed_mapping_approves_without_name_match(normalizer_src: Path) -> None:
    from src.reconciliation.matching import match_kurly_record

    outcome = match_kurly_record(
        _kurly_row(food_name_normalized="다른이름"),
        kfia_rows=[_kfia_row()],
        managed_mappings={"kurly-1": "kfia-1"},
    )
    assert outcome.review_status == "APPROVED"
    assert outcome.match_type == "MANAGED_MAPPING"
    assert outcome.selected_source == "MANUAL"


def test_multi_candidate_requires_review(normalizer_src: Path) -> None:
    from src.reconciliation.matching import match_kurly_record

    outcome = match_kurly_record(
        _kurly_row(),
        kfia_rows=[
            _kfia_row(record_id="kfia-1"),
            _kfia_row(record_id="kfia-2", reference_item_code="17-1-1-2"),
        ],
        managed_mappings={},
    )
    assert outcome.review_status == "REVIEW_REQUIRED"
    assert outcome.match_type == "MULTI_CANDIDATE"
    assert len(outcome.candidate_kfia_record_ids) == 2


def test_build_reconciled_record_validates_contract_fields(normalizer_src: Path) -> None:
    from src.reconciliation.matching import build_reconciled_record, match_kurly_record

    outcome = match_kurly_record(
        _kurly_row(),
        kfia_rows=[_kfia_row()],
        managed_mappings={},
    )
    record = build_reconciled_record(
        kurly_row=_kurly_row(),
        outcome=outcome,
        pair_id="20260830-jaeseong-001__KFIA-2026-08",
        run_id="batch:test:kurly_kfia_reconcile:1",
        parser_version="test",
        created_at="2026-08-30T12:00:00+09:00",
    )
    assert record["source"] == "RECONCILER"
    assert record["review_status"] == "APPROVED"
    assert len(record["content_hash"]) == 64


def test_load_managed_mappings_from_file(normalizer_src: Path, tmp_path) -> None:
    from src.reconciliation.matching import load_managed_mappings

    mapping_path = tmp_path / "default.json"
    mapping_path.write_text(
        '{"schema_version":"1.0.0","mappings":[{"kurly_record_id":"a","kfia_record_id":"b"}]}',
        encoding="utf-8",
    )
    loaded = load_managed_mappings(mapping_path)
    assert loaded == {"a": "b"}
