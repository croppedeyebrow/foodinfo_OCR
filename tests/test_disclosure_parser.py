from __future__ import annotations

from conftest import use_app

use_app("ocr-parser")

from src.disclosure_parser import parse_disclosure_text  # noqa: E402


def test_parse_disclosure_text() -> None:
    result = parse_disclosure_text(
        "식품의 유형 만두류\n소비기한 제조일로부터 9개월\n보관방법 -18℃ 이하 냉동보관"
    )

    assert result.food_type_raw == "만두류"
    assert result.expiration_info_raw == "제조일로부터 9개월"
    assert result.storage_method_raw == "-18℃ 이하 냉동보관"
