from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

from .models import FailureRecord, MergedProductRecord, RawOcrRecord


PRODUCT_COLUMNS = [
    "schema_version",
    "batch_id",
    "source_site",
    "original_product_id",
    "product_name_raw",
    "food_name_candidate",
    "product_url",
    "sales_unit_raw",
    "weight_raw",
    "quantity_raw",
    "food_type_raw",
    "food_type_source",
    "expiration_info_raw",
    "expiration_source",
    "storage_method_raw",
    "storage_source",
    "storage_type",
    "ocr_confidence",
    "crawl_collected_at",
    "ocr_collected_at",
    "parser_version",
    "validation_status",
    "parse_status",
    # 중복 방지용 보조 컬럼
    "source_record_id",
    "image_sha256",
]

FAILURE_COLUMNS = list(FailureRecord.model_fields)


def write_raw_json(record: RawOcrRecord, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / (
        f"{record.original_product_id}_{record.image_sha256[:12]}.json"
    )
    temporary_path = output_path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(
            record.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        ),
        encoding="utf-8",
    )
    temporary_path.replace(output_path)
    return output_path


def append_product_csv(record: MergedProductRecord, output_path: Path) -> None:
    _append_model_csv(record, output_path, PRODUCT_COLUMNS)


def append_failure_csv(record: FailureRecord, output_path: Path) -> None:
    _append_model_csv(record, output_path, FAILURE_COLUMNS)


def load_existing_source_keys(output_path: Path) -> set[str]:
    """배치 CSV에서 이미 기록된 중복 키를 읽는다."""
    if not output_path.exists() or output_path.stat().st_size == 0:
        return set()
    keys: set[str] = set()
    with output_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            site = row.get("source_site") or ""
            product_id = row.get("original_product_id") or ""
            image_hash = row.get("image_sha256") or ""
            source_record_id = row.get("source_record_id") or ""
            if source_record_id:
                keys.add(source_record_id)
            keys.add(f"{site}:{product_id}:{image_hash}")
            keys.add(f"{site}:{product_id}")
    return keys


def build_dedupe_key(
    source_site: str,
    original_product_id: str,
    image_sha256: str | None = None,
) -> str:
    if image_sha256:
        return f"{source_site}:{original_product_id}:{image_sha256}"
    return f"{source_site}:{original_product_id}"


def _append_model_csv(
    record: BaseModel,
    output_path: Path,
    columns: Iterable[str],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(columns)
    should_write_header = not output_path.exists() or output_path.stat().st_size == 0
    payload = record.model_dump(mode="json")

    with output_path.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        if should_write_header:
            writer.writeheader()
        writer.writerow({column: payload.get(column, "") for column in fieldnames})


def _json_default(value: object) -> object:
    if hasattr(value, "tolist"):
        return value.tolist()  # type: ignore[no-any-return, attr-defined]
    if hasattr(value, "item"):
        return value.item()  # type: ignore[no-any-return, attr-defined]
    return str(value)
