from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..checksum import with_content_hash
from ..kurly_transform.text import clean_text

NATIVE_CONTRACT_VERSION = "kfia_native_export_v1.0.0"

_ADAPT_ERROR = "KFIA_ADAPT_FAILED"


@dataclass(slots=True)
class KfiaAdaptError(Exception):
    error_code: str
    message: str
    field: str | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class KfiaBronzeRecord:
    reference_item_code: str
    food_type: str | None
    food_name: str | None
    appearance_raw: str | None
    packaging_raw: str | None
    existing_shelf_life_raw: str | None
    storage_temperature_raw: str | None
    storage_type_raw: str | None
    reference_temperature_raw: str | None
    quality_limit_days: float | None
    safety_factor_raw: str | None
    safety_factor: float | None
    reference_shelf_life_days: float
    original_unit: str
    temperature_details: list[dict[str, Any]]
    source_document: str
    source_page: int
    extracted_at: str
    raw_payload: dict[str, Any]


def _nullable(value: Any) -> str | None:
    if value is None:
        return None
    text = clean_text(str(value))
    return text or None


def _nullable_decimal(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(Decimal(str(value).strip()))
    except (InvalidOperation, ValueError):
        return None


def _required_decimal(value: Any, *, field: str) -> float:
    parsed = _nullable_decimal(value)
    if parsed is None:
        raise KfiaAdaptError(_ADAPT_ERROR, f"{field} must be a number", field)
    return parsed


def _parse_datetime(value: Any) -> str:
    text = _nullable(value)
    if not text:
        raise KfiaAdaptError(_ADAPT_ERROR, "추출일시 is required", "추출일시")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).isoformat(sep=" ")
        except ValueError:
            continue
    return text


def _parse_temperature_details(value: Any) -> list[dict[str, Any]]:
    if value is None or value == "":
        raise KfiaAdaptError(
            _ADAPT_ERROR,
            "온도별_상세_json is required",
            "온도별_상세_json",
        )
    if isinstance(value, list):
        return value
    text = str(value).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise KfiaAdaptError(
            _ADAPT_ERROR,
            f"온도별_상세_json is invalid: {error}",
            "온도별_상세_json",
        ) from error
    if not isinstance(parsed, list):
        raise KfiaAdaptError(
            _ADAPT_ERROR,
            "온도별_상세_json must be a JSON array",
            "온도별_상세_json",
        )
    return parsed


def _parse_source_page(value: Any) -> int:
    if value is None or value == "":
        raise KfiaAdaptError(_ADAPT_ERROR, "source_page is required", "source_page")
    try:
        page = int(float(str(value).strip()))
    except (TypeError, ValueError) as error:
        raise KfiaAdaptError(
            _ADAPT_ERROR,
            "source_page must be a positive integer",
            "source_page",
        ) from error
    if page < 1:
        raise KfiaAdaptError(
            _ADAPT_ERROR,
            "source_page must be a positive integer",
            "source_page",
        )
    return page


def adapt_kfia_native_row(row: dict[str, Any]) -> KfiaBronzeRecord:
    item_code = _nullable(row.get("품목코드"))
    if not item_code:
        raise KfiaAdaptError(_ADAPT_ERROR, "품목코드 is required", "품목코드")

    source_document = _nullable(row.get("source_pdf"))
    if not source_document:
        raise KfiaAdaptError(_ADAPT_ERROR, "source_pdf is required", "source_pdf")

    safety_factor = _nullable_decimal(row.get("안전계수"))
    original_unit = str(row.get("단위", "")).strip()
    if not original_unit:
        raise KfiaAdaptError(_ADAPT_ERROR, "단위 is required", "단위")
    return KfiaBronzeRecord(
        reference_item_code=item_code,
        food_type=_nullable(row.get("식품유형")),
        food_name=None,
        appearance_raw=_nullable(row.get("성상")),
        packaging_raw=_nullable(row.get("포장방법")),
        existing_shelf_life_raw=_nullable(row.get("기존유통기한")),
        storage_temperature_raw=_nullable(row.get("보존유통온도")),
        storage_type_raw=_nullable(row.get("보관방법")),
        reference_temperature_raw=_nullable(row.get("기준온도")),
        quality_limit_days=_nullable_decimal(row.get("품질안전한계기간_일")),
        safety_factor_raw=_nullable(row.get("안전계수")),
        safety_factor=safety_factor,
        reference_shelf_life_days=_required_decimal(
            row.get("소비기한참고값_일"),
            field="소비기한참고값_일",
        ),
        original_unit=original_unit,
        temperature_details=_parse_temperature_details(row.get("온도별_상세_json")),
        source_document=source_document,
        source_page=_parse_source_page(row.get("source_page")),
        extracted_at=_parse_datetime(row.get("추출일시")),
        raw_payload={key: row.get(key) for key in row},
    )


def bronze_record_to_payload(
    record: KfiaBronzeRecord,
    *,
    dataset_version: str,
    run_id: str,
    parser_version: str,
    created_at: str,
    source_row_index: int,
) -> dict[str, Any]:
    source_record_id = f"kfia:{record.reference_item_code}"
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "batch_id": dataset_version,
        "record_id": str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{dataset_version}:{source_record_id}:{source_row_index}",
            )
        ),
        "source": "KFIA",
        "source_record_id": source_record_id,
        "parser_version": parser_version,
        "created_at": created_at,
        "reference_item_code": record.reference_item_code,
        "food_type": record.food_type,
        "food_name": record.food_name,
        "appearance_raw": record.appearance_raw,
        "packaging_raw": record.packaging_raw,
        "existing_shelf_life_raw": record.existing_shelf_life_raw,
        "storage_temperature_raw": record.storage_temperature_raw,
        "storage_type_raw": record.storage_type_raw,
        "reference_temperature_raw": record.reference_temperature_raw,
        "quality_limit_days": record.quality_limit_days,
        "safety_factor_raw": record.safety_factor_raw,
        "safety_factor": record.safety_factor,
        "reference_shelf_life_days": record.reference_shelf_life_days,
        "original_unit": record.original_unit,
        "temperature_details": record.temperature_details,
        "source_document": record.source_document,
        "source_page": record.source_page,
        "extracted_at": record.extracted_at,
        "native_contract_version": NATIVE_CONTRACT_VERSION,
        "source_row_index": source_row_index,
        "raw_payload": record.raw_payload,
    }
    return with_content_hash(payload)
