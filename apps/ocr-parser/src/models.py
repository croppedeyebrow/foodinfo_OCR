from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


def _empty_to_none(value: object) -> object:
    if value == "":
        return None
    return value


class ProductInput(BaseModel):
    batch_id: str
    original_product_id: str
    product_name: str
    product_url: HttpUrl
    image_path: str | None = None
    source_image_url: HttpUrl | None = None
    source_site: str = "KURLY"
    expiration_info_dom: str | None = None
    storage_method_dom: str | None = None
    storage_type_dom: str | None = None
    food_name_candidate: str | None = None
    weight_raw: str | None = None
    quantity_raw: str | None = None
    sales_unit_raw: str | None = None
    crawl_collected_at: datetime | None = None

    @field_validator(
        "image_path",
        "source_image_url",
        "expiration_info_dom",
        "storage_method_dom",
        "storage_type_dom",
        "food_name_candidate",
        "weight_raw",
        "quantity_raw",
        "sales_unit_raw",
        mode="before",
    )
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        return _empty_to_none(value)


class OcrTextBlock(BaseModel):
    text: str
    confidence: float | None = None
    polygon: list[list[float]] | None = None


class RawOcrRecord(BaseModel):
    schema_version: str = "1.0"
    source_record_id: str
    source_site: str
    batch_id: str
    original_product_id: str
    product_name: str
    product_url: str
    source_image_url: str | None = None
    local_image_name: str
    image_sha256: str
    ocr_engine: str
    ocr_engine_version: str
    ocr_confidence: float | None = None
    ocr_raw_text: str
    text_blocks: list[OcrTextBlock] = Field(default_factory=list)
    engine_raw_result: Any | None = None
    collected_at: datetime


class ParsedDisclosureFields(BaseModel):
    food_type_raw: str | None = None
    expiration_info_raw: str | None = None
    storage_method_raw: str | None = None


class MergedProductRecord(BaseModel):
    schema_version: str = "1.0"
    batch_id: str
    source_site: str
    original_product_id: str
    product_name_raw: str
    food_name_candidate: str | None = None
    product_url: str
    sales_unit_raw: str | None = None
    weight_raw: str | None = None
    quantity_raw: str | None = None
    food_type_raw: str | None = None
    food_type_source: str = "NOT_FOUND"
    expiration_info_raw: str | None = None
    expiration_source: str = "NOT_FOUND"
    storage_method_raw: str | None = None
    storage_source: str = "NOT_FOUND"
    storage_type: str = "UNKNOWN"
    ocr_confidence: float | None = None
    crawl_collected_at: datetime | None = None
    ocr_collected_at: datetime | None = None
    parser_version: str
    validation_status: str
    parse_status: str
    source_record_id: str | None = None
    image_sha256: str | None = None


# 기존 CSV/테스트 호환을 위해 별칭 유지
class ParsedProductRecord(MergedProductRecord):
    source_image_url: str | None = None
    ocr_engine: str | None = None
    ocr_engine_version: str | None = None
    collected_at: datetime | None = None


class OcrFailureRecord(BaseModel):
    batch_id: str
    source_site: str
    original_product_id: str
    product_name: str
    product_url: str
    image_path: str
    error_code: str
    error_message: str
    failed_at: datetime


# 기존 코드 호환
FailureRecord = OcrFailureRecord
