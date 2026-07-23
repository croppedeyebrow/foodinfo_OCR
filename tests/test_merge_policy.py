from __future__ import annotations

from conftest import use_app

use_app("ocr-parser")

from src.merge_policy import (  # noqa: E402
    STATUS_FIELD_NOT_FOUND,
    STATUS_MATCHED,
    STATUS_REVIEW,
    SOURCE_BOTH,
    SOURCE_DOM,
    SOURCE_OCR,
    mark_review_when_dom_and_ocr_conflict,
    select_dom_value_when_ocr_missing,
    select_ocr_value_when_dom_missing,
)


def test_select_dom_value_when_ocr_missing() -> None:
    result = select_dom_value_when_ocr_missing(
        "수령일 포함 최소 3일 남은 제품",
        None,
    )
    assert result.value == "수령일 포함 최소 3일 남은 제품"
    assert result.source == SOURCE_DOM
    assert result.validation_status == STATUS_MATCHED


def test_select_ocr_value_when_dom_missing() -> None:
    result = select_ocr_value_when_dom_missing(None, "별도 표시일까지")
    assert result.value == "별도 표시일까지"
    assert result.source == SOURCE_OCR
    assert result.validation_status == STATUS_MATCHED


def test_mark_review_when_dom_and_ocr_conflict() -> None:
    result = mark_review_when_dom_and_ocr_conflict(
        "수령일 포함 최소 3일 남은 제품",
        "별도 표시일까지",
    )
    assert result.value == "수령일 포함 최소 3일 남은 제품"
    assert result.source == SOURCE_DOM
    assert result.validation_status == STATUS_REVIEW


def test_matched_when_semantically_equal() -> None:
    result = mark_review_when_dom_and_ocr_conflict(
        "-2~10℃에서 즉시 냉장 보관하세요.",
        "-2~10℃ 냉장보관",
    )
    assert result.source == SOURCE_BOTH
    assert result.validation_status == STATUS_MATCHED


def test_field_not_found_when_both_missing() -> None:
    result = select_dom_value_when_ocr_missing(None, None)
    assert result.value is None
    assert result.validation_status == STATUS_FIELD_NOT_FOUND
