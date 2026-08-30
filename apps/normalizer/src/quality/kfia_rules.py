from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

QualitySeverity = Literal["REJECTED", "REVIEW_REQUIRED"]
ReviewStatus = Literal["APPROVED", "REVIEW_REQUIRED", "REJECTED"]

QUALITY_RULE_VERSION = "kfia_quality_v1.0.0"

_STORAGE_ALIASES = {
    "냉장": "REFRIGERATED",
    "냉동": "FROZEN",
    "실온": "AMBIENT",
    "상온": "AMBIENT",
}


@dataclass(frozen=True, slots=True)
class KfiaQualityFinding:
    rule_id: str
    severity: QualitySeverity
    message: str


def normalize_kfia_storage_type(storage_type_raw: str | None) -> tuple[str, bool]:
    cleaned = (storage_type_raw or "").strip()
    if not cleaned:
        return "UNKNOWN", True
    if cleaned in _STORAGE_ALIASES:
        return _STORAGE_ALIASES[cleaned], False
    return "UNKNOWN", True


def _pdf_category_number(source_document: str) -> int | None:
    match = re.match(r"^\s*(\d+)\s*\.", source_document.strip())
    if match is None:
        return None
    return int(match.group(1))


def _item_code_category(reference_item_code: str) -> int | None:
    first = reference_item_code.strip().split("-", 1)[0]
    if not first.isdigit():
        return None
    return int(first)


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def evaluate_kfia_quality(record: dict[str, Any]) -> tuple[ReviewStatus, list[KfiaQualityFinding]]:
    findings: list[KfiaQualityFinding] = []
    item_code = str(record.get("reference_item_code") or "").strip()
    if not item_code:
        findings.append(
            KfiaQualityFinding("KFIA-001", "REJECTED", "품목코드가 없습니다.")
        )

    shelf_life = record.get("reference_shelf_life_days")
    shelf_decimal = _parse_decimal(shelf_life)
    if shelf_decimal is None or shelf_decimal <= 0:
        findings.append(
            KfiaQualityFinding(
                "KFIA-002",
                "REJECTED",
                "소비기한 참고값이 양수가 아닙니다.",
            )
        )

    safety_factor = _parse_decimal(record.get("safety_factor"))
    if safety_factor is not None and safety_factor > Decimal("1"):
        findings.append(
            KfiaQualityFinding(
                "KFIA-003",
                "REVIEW_REQUIRED",
                "안전계수가 1을 초과합니다.",
            )
        )

    source_document = str(record.get("source_document") or "").strip()
    source_page = record.get("source_page")
    if not source_document or source_page in {None, ""}:
        findings.append(
            KfiaQualityFinding(
                "KFIA-008",
                "REJECTED",
                "source PDF 또는 page가 없습니다.",
            )
        )
    else:
        pdf_category = _pdf_category_number(source_document)
        item_category = _item_code_category(item_code) if item_code else None
        if (
            pdf_category is not None
            and item_category is not None
            and pdf_category != item_category
        ):
            findings.append(
                KfiaQualityFinding(
                    "KFIA-004",
                    "REVIEW_REQUIRED",
                    "품목코드 분류와 source PDF 분류가 일치하지 않습니다.",
                )
            )

    temperature_details = record.get("temperature_details")
    if not isinstance(temperature_details, list):
        findings.append(
            KfiaQualityFinding(
                "KFIA-005",
                "REJECTED",
                "온도별 상세 JSON이 유효하지 않습니다.",
            )
        )

    storage_type_raw = record.get("storage_type_raw")
    _storage_type, storage_review = normalize_kfia_storage_type(
        str(storage_type_raw) if storage_type_raw is not None else None
    )
    if storage_review:
        findings.append(
            KfiaQualityFinding(
                "KFIA-006",
                "REVIEW_REQUIRED",
                "보관방법을 표준화할 수 없습니다.",
            )
        )

    food_type = str(record.get("food_type") or "").strip()
    storage_raw = str(storage_type_raw or "").strip()
    if not food_type or not storage_raw:
        findings.append(
            KfiaQualityFinding(
                "KFIA-007",
                "REVIEW_REQUIRED",
                "식품유형 또는 보관방법이 비어 있습니다.",
            )
        )

    if any(item.severity == "REJECTED" for item in findings):
        return "REJECTED", findings
    if findings:
        return "REVIEW_REQUIRED", findings
    return "APPROVED", findings


def summarize_quality_counts(statuses: list[ReviewStatus]) -> dict[str, int]:
    return {
        "approved_count": sum(1 for item in statuses if item == "APPROVED"),
        "review_required_count": sum(1 for item in statuses if item == "REVIEW_REQUIRED"),
        "rejected_count": sum(1 for item in statuses if item == "REJECTED"),
    }
