from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import use_app

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "kfia"
NATIVE_SAMPLE = FIXTURES / "shelf_life_output.native.sample.csv"


@pytest.fixture()
def normalizer_src() -> Path:
    return use_app("normalizer")


def test_native_export_headers_pass_contract(normalizer_src: Path) -> None:
    from src.kfia_export_columns import read_native_export, summarize_native_export
    from src.reference_registration import validate_reference_export

    summary = validate_reference_export(NATIVE_SAMPLE)
    assert summary["row_count"] == 3
    assert summary["required_columns_present"] is True
    assert "food_name" not in summary["missing_columns"]
    assert summary["checks"]["raw_text"] == "미제공 · 선택 필드"

    frame = read_native_export(NATIVE_SAMPLE)
    native_summary = summarize_native_export(frame)
    assert native_summary["verdict"].startswith("Native 계약 통과")


def test_adapter_maps_native_row_without_food_name(normalizer_src: Path) -> None:
    from src.adapters.kfia_native_csv import adapt_kfia_native_row, bronze_record_to_payload
    from src.kfia_export_columns import read_native_export

    row = read_native_export(NATIVE_SAMPLE).to_dicts()[0]
    adapted = adapt_kfia_native_row(row)
    assert adapted.food_type == "일반환자용 균형영양조제식품"
    assert adapted.food_name is None
    assert adapted.source_page == 9
    assert isinstance(adapted.temperature_details, list)

    payload = bronze_record_to_payload(
        adapted,
        dataset_version="KFIA-2026-08",
        run_id="run-1",
        parser_version="dev",
        created_at="2026-08-30T00:00:00",
        source_row_index=0,
    )
    assert payload["source"] == "KFIA"
    assert payload["food_name"] is None


def test_quality_rules_flag_safety_factor_and_pdf_mismatch(normalizer_src: Path) -> None:
    from src.adapters.kfia_native_csv import adapt_kfia_native_row, bronze_record_to_payload
    from src.kfia_export_columns import read_native_export
    from src.quality.kfia_rules import evaluate_kfia_quality

    rows = read_native_export(NATIVE_SAMPLE).to_dicts()
    high_sf = bronze_record_to_payload(
        adapt_kfia_native_row(rows[0]),
        dataset_version="KFIA-2026-08",
        run_id="run-1",
        parser_version="dev",
        created_at="2026-08-30T00:00:00",
        source_row_index=0,
    )
    status, findings = evaluate_kfia_quality(high_sf)
    assert status == "REVIEW_REQUIRED"
    assert any(item.rule_id == "KFIA-003" for item in findings)

    mismatch = bronze_record_to_payload(
        adapt_kfia_native_row(rows[2]),
        dataset_version="KFIA-2026-08",
        run_id="run-1",
        parser_version="dev",
        created_at="2026-08-30T00:00:00",
        source_row_index=2,
    )
    status, findings = evaluate_kfia_quality(mismatch)
    assert status == "REVIEW_REQUIRED"
    assert any(item.rule_id == "KFIA-004" for item in findings)


def test_invalid_temperature_json_is_rejected(normalizer_src: Path) -> None:
    from src.adapters.kfia_native_csv import KfiaAdaptError, adapt_kfia_native_row

    row = {
        "품목코드": "X-1",
        "식품유형": "테스트",
        "소비기한참고값_일": "10",
        "단위": "일",
        "온도별_상세_json": "{not-json",
        "source_pdf": "1. 테스트.pdf",
        "source_page": "1",
        "추출일시": "2026-07-03 21:54:05",
    }
    with pytest.raises(KfiaAdaptError):
        adapt_kfia_native_row(row)


def test_utf8_bom_header_is_supported(normalizer_src: Path, tmp_path: Path) -> None:
    from src.kfia_export_columns import read_native_export
    from src.reference_registration import validate_reference_export

    bom_path = tmp_path / "bom.csv"
    bom_path.write_bytes(NATIVE_SAMPLE.read_bytes())
    summary = validate_reference_export(bom_path)
    assert summary["required_columns_present"] is True
    frame = read_native_export(bom_path)
    assert "품목코드" in frame.columns
