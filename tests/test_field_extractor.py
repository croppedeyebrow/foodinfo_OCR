from __future__ import annotations

from conftest import use_app

use_app("crawler")

from src.field_extractor import (  # noqa: E402
    build_food_name_candidate,
    extract_expiration_info,
    extract_labeled_text,
    extract_quantity,
    extract_storage_method,
    normalize_storage_type,
)


SAMPLE_TEXT = """
판매단위 1팩
중량/용량 250g
수량 2개입
소비기한 수령일 포함 최소 3일 남은 제품을 보내 드립니다.
보관방법 -2~10℃에서 즉시 냉장 보관하세요.
"""


def test_extract_labeled_text() -> None:
    assert extract_labeled_text(SAMPLE_TEXT, ("판매단위",)) == "1팩"
    assert (
        extract_labeled_text(SAMPLE_TEXT, ("소비기한",))
        == "수령일 포함 최소 3일 남은 제품을 보내 드립니다."
    )
    assert (
        extract_labeled_text(SAMPLE_TEXT, ("보관방법",))
        == "-2~10℃에서 즉시 냉장 보관하세요."
    )


def test_extract_kurly_multiline_labels() -> None:
    page_text = """
판매단위
1팩
중량/용량
250g
소비기한(또는 유통기한)정보
수령일 포함 최소 3일 남은 제품을 보내 드립니다.
구매 수량
・중량 : 1팩(250g / 2개입)
・보관법 : -2~10℃에서 즉시 냉장 보관하세요.
보관방법 또는 취급방법
상품설명 및 상품이미지 참조
"""
    assert extract_expiration_info(page_text) == (
        "수령일 포함 최소 3일 남은 제품을 보내 드립니다."
    )
    assert extract_storage_method(page_text) == (
        "-2~10℃에서 즉시 냉장 보관하세요."
    )
    assert extract_quantity(page_text) == "2개입"


def test_normalize_storage_type() -> None:
    assert normalize_storage_type("안심 스테이크 250g (냉장)") == "REFRIGERATED"
    assert normalize_storage_type("-18℃ 냉동 보관") == "FROZEN"
    assert normalize_storage_type("상온 보관") == "ROOM_TEMPERATURE"
    assert normalize_storage_type(None, "") == "UNKNOWN"


def test_build_food_name_candidate() -> None:
    name = "[델리치오] 호주산 소고기 목초육 안심 스테이크 250g (냉장)"
    assert build_food_name_candidate(name) == "소고기 안심 스테이크"
