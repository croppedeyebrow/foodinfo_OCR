"""Compatibility adapter: existing outcome products.csv → collection_submission."""

from __future__ import annotations

import csv
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..checksum import with_content_hash
from ..contracts import CollectionSubmission

KST = ZoneInfo("Asia/Seoul")

# Existing products.csv columns from ocr-parser PRODUCT_COLUMNS — do not drop.
LEGACY_PRODUCT_COLUMNS = [
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
    "source_record_id",
    "image_sha256",
]


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text if text else None


def _parse_optional_float(value: str | None) -> float | None:
    text = _blank_to_none(value)
    if text is None:
        return None
    return float(text)


def _row_to_product(
    row: dict[str, str],
    *,
    run_id: str,
    created_at: str,
    fallback_batch_id: str,
) -> dict[str, Any]:
    batch_id = _blank_to_none(row.get("batch_id")) or fallback_batch_id
    original_product_id = _blank_to_none(row.get("original_product_id")) or ""
    source_site = _blank_to_none(row.get("source_site")) or "KURLY"
    source_record_id = (
        _blank_to_none(row.get("source_record_id"))
        or f"{source_site}:{original_product_id}"
    )
    parser_version = _blank_to_none(row.get("parser_version")) or "0.0.0"
    product_name = _blank_to_none(row.get("product_name_raw")) or ""
    product_url = _blank_to_none(row.get("product_url")) or ""

    product: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "batch_id": batch_id,
        "record_id": f"{batch_id}:{source_record_id}",
        "source": source_site,
        "source_record_id": source_record_id,
        "source_uri": product_url or None,
        "parser_version": parser_version,
        "created_at": created_at,
        "original_product_id": original_product_id,
        "product_name_raw": product_name,
        "product_url": product_url,
        "food_name_candidate": _blank_to_none(row.get("food_name_candidate")),
        "sales_unit_raw": _blank_to_none(row.get("sales_unit_raw")),
        "weight_raw": _blank_to_none(row.get("weight_raw")),
        "quantity_raw": _blank_to_none(row.get("quantity_raw")),
        "food_type_raw": _blank_to_none(row.get("food_type_raw")),
        "food_type_source": _blank_to_none(row.get("food_type_source")),
        "expiration_info_raw": _blank_to_none(row.get("expiration_info_raw")),
        "expiration_source": _blank_to_none(row.get("expiration_source")),
        "storage_method_raw": _blank_to_none(row.get("storage_method_raw")),
        "storage_source": _blank_to_none(row.get("storage_source")),
        "storage_type": _blank_to_none(row.get("storage_type")),
        "ocr_confidence": _parse_optional_float(row.get("ocr_confidence")),
        "crawl_collected_at": _blank_to_none(row.get("crawl_collected_at")),
        "ocr_collected_at": _blank_to_none(row.get("ocr_collected_at")),
        "validation_status": _blank_to_none(row.get("validation_status")),
        "parse_status": _blank_to_none(row.get("parse_status")),
        "image_sha256": _blank_to_none(row.get("image_sha256")),
    }
    # Preserve unknown legacy columns without inventing meanings.
    known = set(product.keys()) | set(LEGACY_PRODUCT_COLUMNS)
    for key, value in row.items():
        if key not in known:
            product[key] = _blank_to_none(value)
    return with_content_hash(product)


def adapt_products_csv(
    products_csv: Path,
    *,
    batch_id: str,
    member: str,
    run_id: str | None = None,
    status: str = "DRAFT",
    failures_csv: Path | None = None,
    discovery_dir: Path | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Convert existing products.csv into a sealed collection_submission dict."""
    if not products_csv.is_file():
        raise FileNotFoundError(f"products.csv not found: {products_csv}")

    run = run_id or str(uuid.uuid4())
    created = (created_at or datetime.now(KST)).isoformat()

    with products_csv.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    products = [
        _row_to_product(row, run_id=run, created_at=created, fallback_batch_id=batch_id)
        for row in rows
    ]

    artifacts: dict[str, Any] = {
        "products_csv_uri": products_csv.as_posix(),
        "failures_csv_uri": failures_csv.as_posix() if failures_csv else None,
        "discovery_dir_uri": discovery_dir.as_posix() if discovery_dir else None,
    }

    submission = {
        "schema_version": "1.0.0",
        "run_id": run,
        "batch_id": batch_id,
        "record_id": f"submission:{member}:{batch_id}:{run}",
        "source": "KURLY_COLLECTION",
        "source_record_id": f"{member}:{batch_id}",
        "source_uri": products_csv.as_posix(),
        "parser_version": products[0]["parser_version"] if products else "0.0.0",
        "created_at": created,
        "member": member,
        "status": status,
        "row_count": len(products),
        "supported_consumer_versions": ["1.0.0"],
        "artifacts": artifacts,
        "products": products,
    }
    sealed = with_content_hash(submission)
    # Ensure pydantic shape before return.
    CollectionSubmission.model_validate(sealed)
    return sealed


def write_submission_json(payload: dict[str, Any], output_path: Path) -> Path:
    import json

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path
