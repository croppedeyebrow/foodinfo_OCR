from __future__ import annotations

import re
from dataclasses import dataclass


SOURCE_DOM = "DOM"
SOURCE_OCR = "OCR"
SOURCE_BOTH = "DOM_AND_OCR"
SOURCE_NOT_FOUND = "NOT_FOUND"

STATUS_MATCHED = "MATCHED"
STATUS_REVIEW = "REVIEW_REQUIRED"
STATUS_FIELD_NOT_FOUND = "FIELD_NOT_FOUND"
STATUS_COMPLETED = "COMPLETED"


CLOSING_PHRASES = (
    "하세요",
    "하십시오",
    "보관하세요",
    "보관하십시오",
    "바랍니다",
)

FILLER_WORDS = (
    "에서",
    "즉시",
    "바로",
    "반드시",
    "해주세요",
    "해 주세요",
)


@dataclass(slots=True)
class MergedField:
    value: str | None
    source: str
    validation_status: str


def normalize_for_compare(text: str | None) -> str:
    if not text:
        return ""
    normalized = text.lower()
    normalized = normalized.replace("℃", "도").replace("°c", "도")
    for phrase in CLOSING_PHRASES + FILLER_WORDS:
        normalized = normalized.replace(phrase, "")
    normalized = re.sub(r"[\s\|:：\-_/.,·•()\[\]{}~～]", "", normalized)
    return normalized


def values_semantically_equal(left: str | None, right: str | None) -> bool:
    left_norm = normalize_for_compare(left)
    right_norm = normalize_for_compare(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    if left_norm in right_norm or right_norm in left_norm:
        return True
    # 숫자·온도 구간과 핵심 키워드(냉장/냉동 등)가 같으면 의미 일치로 본다
    left_tokens = set(re.findall(r"\d+|냉장|냉동|상온|실온|보관", left_norm))
    right_tokens = set(re.findall(r"\d+|냉장|냉동|상온|실온|보관", right_norm))
    return bool(left_tokens) and left_tokens == right_tokens


def merge_field(dom_value: str | None, ocr_value: str | None) -> MergedField:
    has_dom = bool(dom_value and dom_value.strip())
    has_ocr = bool(ocr_value and ocr_value.strip())

    if has_dom and not has_ocr:
        return MergedField(dom_value.strip(), SOURCE_DOM, STATUS_MATCHED)
    if has_ocr and not has_dom:
        return MergedField(ocr_value.strip(), SOURCE_OCR, STATUS_MATCHED)
    if not has_dom and not has_ocr:
        return MergedField(None, SOURCE_NOT_FOUND, STATUS_FIELD_NOT_FOUND)

    assert dom_value is not None and ocr_value is not None
    if values_semantically_equal(dom_value, ocr_value):
        return MergedField(dom_value.strip(), SOURCE_BOTH, STATUS_MATCHED)
    return MergedField(dom_value.strip(), SOURCE_DOM, STATUS_REVIEW)


def select_dom_value_when_ocr_missing(dom_value: str | None, ocr_value: str | None) -> MergedField:
    return merge_field(dom_value, ocr_value)


def select_ocr_value_when_dom_missing(dom_value: str | None, ocr_value: str | None) -> MergedField:
    return merge_field(dom_value, ocr_value)


def mark_review_when_dom_and_ocr_conflict(
    dom_value: str | None,
    ocr_value: str | None,
) -> MergedField:
    return merge_field(dom_value, ocr_value)


def overall_validation_status(*field_statuses: str) -> str:
    if any(status == STATUS_REVIEW for status in field_statuses):
        return STATUS_REVIEW
    if field_statuses and all(status == STATUS_FIELD_NOT_FOUND for status in field_statuses):
        return STATUS_FIELD_NOT_FOUND
    return STATUS_MATCHED
