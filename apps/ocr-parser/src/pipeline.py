from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .checksum import calculate_sha256
from .disclosure_parser import parse_disclosure_text
from .exporter import (
    append_product_csv,
    build_dedupe_key,
    load_existing_source_keys,
    write_raw_json,
)
from .merge_policy import merge_field, overall_validation_status
from .models import MergedProductRecord, ProductInput, RawOcrRecord
from .ocr_engine import PaddleOcrEngine


KST = ZoneInfo("Asia/Seoul")

TARGET_FIELD_KEYWORDS = (
    "소비기한",
    "유통기한",
    "보관방법",
    "보관",
    "식품유형",
    "식품의 유형",
)


class ProductOcrPipeline:
    def __init__(self, parser_version: str = "0.1.0", language: str = "korean") -> None:
        self.parser_version = parser_version
        self.language = language
        self._engine: PaddleOcrEngine | None = None
        self._seen_keys_by_batch: dict[str, set[str]] = {}

    @property
    def engine(self) -> PaddleOcrEngine:
        if self._engine is None:
            self._engine = PaddleOcrEngine(language=self.language)
        return self._engine

    def _keys_for_batch(self, batch_id: str, csv_path: Path) -> set[str]:
        if batch_id not in self._seen_keys_by_batch:
            self._seen_keys_by_batch[batch_id] = load_existing_source_keys(csv_path)
        return self._seen_keys_by_batch[batch_id]

    def process(self, product: ProductInput, data_root: Path) -> tuple[Path | None, Path]:
        outcome_root = Path(os.getenv("OUTCOME_ROOT", "/outcome"))
        member = os.getenv("BATCH_MEMBER", "unknown")
        batch_dir = outcome_root / member / product.batch_id
        csv_path = batch_dir / "products.csv"
        self._keys_for_batch(product.batch_id, csv_path)

        has_image = bool(product.image_path and str(product.image_path).strip())
        if has_image:
            return self._process_with_image(product, data_root, csv_path)
        return self._process_dom_only(product, csv_path)

    def _process_dom_only(
        self,
        product: ProductInput,
        csv_path: Path,
    ) -> tuple[Path | None, Path]:
        seen = self._keys_for_batch(product.batch_id, csv_path)
        dedupe_key = build_dedupe_key(product.source_site, product.original_product_id)
        if dedupe_key in seen:
            return None, csv_path

        food_type = merge_field(None, None)
        expiration = merge_field(product.expiration_info_dom, None)
        storage = merge_field(product.storage_method_dom, None)
        validation = overall_validation_status(
            food_type.validation_status,
            expiration.validation_status,
            storage.validation_status,
        )
        parse_status = (
            "COMPLETED"
            if any((expiration.value, storage.value, product.product_name))
            else "FIELD_PARSE_FAILED"
        )
        record = self._build_merged_record(
            product=product,
            food_type=food_type,
            expiration=expiration,
            storage=storage,
            storage_type=product.storage_type_dom or "UNKNOWN",
            ocr_confidence=None,
            ocr_collected_at=None,
            source_record_id=f"{product.source_site}:{product.original_product_id}",
            image_sha256=None,
            validation_status=validation,
            parse_status=parse_status,
        )
        append_product_csv(record, csv_path)
        seen.add(dedupe_key)
        return None, csv_path

    def _process_with_image(
        self,
        product: ProductInput,
        data_root: Path,
        csv_path: Path,
    ) -> tuple[Path | None, Path]:
        image_path = Path(str(product.image_path))
        if not image_path.is_absolute():
            image_path = data_root / str(product.image_path)
        if not image_path.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")

        image_hash = calculate_sha256(image_path)
        source_record_id = (
            f"{product.source_site}:{product.original_product_id}:{image_hash[:12]}"
        )
        dedupe_key = build_dedupe_key(
            product.source_site,
            product.original_product_id,
            image_hash,
        )
        seen = self._keys_for_batch(product.batch_id, csv_path)
        if dedupe_key in seen or source_record_id in seen:
            return None, csv_path

        collected_at = datetime.now(KST)
        ocr_result = self.engine.recognize(image_path)
        if not ocr_result.full_text.strip():
            raise ValueError("OCR_TEXT_EMPTY")

        raw_record = RawOcrRecord(
            source_record_id=source_record_id,
            source_site=product.source_site,
            batch_id=product.batch_id,
            original_product_id=product.original_product_id,
            product_name=product.product_name,
            product_url=str(product.product_url),
            source_image_url=(
                str(product.source_image_url) if product.source_image_url else None
            ),
            local_image_name=image_path.name,
            image_sha256=image_hash,
            ocr_engine=self.engine.name,
            ocr_engine_version=self.engine.version,
            ocr_confidence=ocr_result.confidence,
            ocr_raw_text=ocr_result.full_text,
            text_blocks=ocr_result.blocks,
            engine_raw_result=ocr_result.raw_result,
            collected_at=collected_at,
        )
        raw_path = write_raw_json(raw_record, data_root / "ocr_raw")

        if not _has_target_fields(ocr_result.full_text):
            seen.add(dedupe_key)
            seen.add(source_record_id)
            if product.expiration_info_dom or product.storage_method_dom:
                product_key = build_dedupe_key(
                    product.source_site,
                    product.original_product_id,
                )
                if product_key not in seen:
                    _, csv_path = self._process_dom_only(product, csv_path)
            return raw_path, csv_path

        fields = parse_disclosure_text(ocr_result.full_text)
        food_type = merge_field(None, fields.food_type_raw)
        expiration = merge_field(product.expiration_info_dom, fields.expiration_info_raw)
        storage = merge_field(product.storage_method_dom, fields.storage_method_raw)
        validation = overall_validation_status(
            food_type.validation_status,
            expiration.validation_status,
            storage.validation_status,
        )
        parse_status = (
            "COMPLETED"
            if any((food_type.value, expiration.value, storage.value))
            else "FIELD_PARSE_FAILED"
        )
        storage_type = product.storage_type_dom or _infer_storage_type(
            storage.value,
            product.product_name,
        )

        record = self._build_merged_record(
            product=product,
            food_type=food_type,
            expiration=expiration,
            storage=storage,
            storage_type=storage_type,
            ocr_confidence=ocr_result.confidence,
            ocr_collected_at=collected_at,
            source_record_id=source_record_id,
            image_sha256=image_hash,
            validation_status=validation,
            parse_status=parse_status,
        )
        append_product_csv(record, csv_path)
        seen.add(dedupe_key)
        seen.add(source_record_id)
        return raw_path, csv_path

    def _build_merged_record(
        self,
        *,
        product: ProductInput,
        food_type,
        expiration,
        storage,
        storage_type: str,
        ocr_confidence: float | None,
        ocr_collected_at: datetime | None,
        source_record_id: str | None,
        image_sha256: str | None,
        validation_status: str,
        parse_status: str,
    ) -> MergedProductRecord:
        return MergedProductRecord(
            batch_id=product.batch_id,
            source_site=product.source_site,
            original_product_id=product.original_product_id,
            product_name_raw=product.product_name,
            food_name_candidate=product.food_name_candidate,
            product_url=str(product.product_url),
            sales_unit_raw=product.sales_unit_raw,
            weight_raw=product.weight_raw,
            quantity_raw=product.quantity_raw,
            food_type_raw=food_type.value,
            food_type_source=food_type.source,
            expiration_info_raw=expiration.value,
            expiration_source=expiration.source,
            storage_method_raw=storage.value,
            storage_source=storage.source,
            storage_type=storage_type,
            ocr_confidence=ocr_confidence,
            crawl_collected_at=product.crawl_collected_at,
            ocr_collected_at=ocr_collected_at,
            parser_version=self.parser_version,
            validation_status=validation_status,
            parse_status=parse_status,
            source_record_id=source_record_id,
            image_sha256=image_sha256,
        )


def _has_target_fields(text: str) -> bool:
    compact = text.replace(" ", "")
    return any(keyword.replace(" ", "") in compact for keyword in TARGET_FIELD_KEYWORDS)


def _infer_storage_type(*texts: str | None) -> str:
    combined = " ".join(text for text in texts if text).lower()
    if "냉동" in combined:
        return "FROZEN"
    if "냉장" in combined:
        return "REFRIGERATED"
    if "상온" in combined or "실온" in combined:
        return "ROOM_TEMPERATURE"
    return "UNKNOWN"
