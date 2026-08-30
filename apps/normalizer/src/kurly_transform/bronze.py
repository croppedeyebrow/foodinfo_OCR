from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from ..checksum import with_content_hash
from ..contracts import validate_payload
from ..storage_paths import accepted_inbox_dir, bronze_batch_dir, quarantine_run_dir
from ..submission import file_sha256
from .common import (
    atomic_write_json,
    atomic_write_jsonl,
    atomic_write_parquet,
    now_iso,
    parquet_checksum,
    promote_staging,
    staging_dir,
)
from .text import is_dom_source

EVIDENCE_FIELDS = (
    "expiration_info_raw",
    "expiration_source",
    "storage_method_raw",
    "storage_source",
    "storage_type",
    "ocr_confidence",
    "food_type_raw",
    "food_type_source",
    "crawl_collected_at",
    "ocr_collected_at",
    "validation_status",
    "parse_status",
    "image_sha256",
)


@dataclass(slots=True)
class BronzeBatchResult:
    input_count: int
    valid_count: int
    quarantine_count: int
    batch_dir: Path
    manifest_path: Path
    products_path: Path
    quarantine_path: Path | None


def _accepted_manifest_path(data_root: Path, batch_id: str) -> Path:
    return accepted_inbox_dir(data_root, batch_id) / "manifest.json"


def _submitted_product_to_bronze(
    product: dict[str, Any],
    *,
    batch_id: str,
    run_id: str,
    parser_version: str,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "batch_id": batch_id,
        "record_id": product["record_id"],
        "source": "KURLY",
        "source_record_id": product["source_record_id"],
        "source_uri": product.get("product_url"),
        "parser_version": parser_version,
        "created_at": product.get("created_at") or now_iso(),
        "original_product_id": str(product["original_product_id"]),
        "product_name_raw": product.get("product_name_raw"),
        "product_url": product["product_url"],
        "food_name_candidate": product.get("food_name_candidate"),
        "sales_unit_raw": product.get("sales_unit_raw"),
        "weight_raw": product.get("weight_raw"),
        "quantity_raw": product.get("quantity_raw"),
        "collected_at": product.get("crawl_collected_at") or product.get("ocr_collected_at"),
        "crawl_status": product.get("parse_status") or product.get("validation_status"),
    }
    if is_dom_source(product.get("expiration_source")):
        record["expiration_info_dom"] = product.get("expiration_info_raw")
    if is_dom_source(product.get("storage_source")):
        record["storage_method_dom"] = product.get("storage_method_raw")
    record["storage_type_dom"] = product.get("storage_type")
    for key in EVIDENCE_FIELDS:
        value = product.get(key)
        if value is not None and value != "":
            record[key] = value
    return with_content_hash(record)


def run_kurly_bronze(
    *,
    data_root: Path,
    batch_id: str,
    run_id: str,
    code_version: str,
    attempt: int,
) -> BronzeBatchResult:
    manifest_path = _accepted_manifest_path(data_root, batch_id)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"accepted manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if str(manifest.get("status", "")).upper() != "ACCEPTED":
        raise ValueError("accepted manifest status must be ACCEPTED")

    manifest_checksum = file_sha256(manifest_path)
    stored_checksum = manifest.get("content_hash")
    if stored_checksum:
        validation = validate_payload("collection_submission", manifest)
        if not validation.ok:
            raise ValueError(
                "accepted manifest checksum/contract validation failed: "
                + "; ".join(issue.message for issue in validation.issues[:3])
            )

    products = manifest.get("products") or []
    parser_version = str(manifest.get("parser_version") or code_version)
    valid_records: list[dict[str, Any]] = []
    quarantine_records: list[dict[str, Any]] = []

    for index, product in enumerate(products):
        if not isinstance(product, dict):
            quarantine_records.append(
                {
                    "index": index,
                    "error_code": "INVALID_PRODUCT_ROW",
                    "message": "product row must be an object",
                    "payload": product,
                }
            )
            continue
        try:
            bronze_record = _submitted_product_to_bronze(
                product,
                batch_id=batch_id,
                run_id=run_id,
                parser_version=parser_version,
            )
        except (KeyError, TypeError, ValueError) as error:
            quarantine_records.append(
                {
                    "index": index,
                    "record_id": product.get("record_id"),
                    "error_code": "BRONZE_MAPPING_FAILED",
                    "message": str(error),
                    "payload": product,
                }
            )
            continue
        validation = validate_payload("kurly_raw_product", bronze_record)
        if not validation.ok:
            quarantine_records.append(
                {
                    "index": index,
                    "record_id": bronze_record.get("record_id"),
                    "error_code": validation.issues[0].error_code,
                    "message": validation.issues[0].message,
                    "payload": bronze_record,
                }
            )
            continue
        valid_records.append(bronze_record)

    batch_dir = bronze_batch_dir(data_root, "kurly", batch_id)
    staging = staging_dir(batch_dir, attempt)
    staging.mkdir(parents=True, exist_ok=True)

    products_path = staging / "products.parquet"
    if valid_records:
        atomic_write_parquet(products_path, pl.DataFrame(valid_records))
    else:
        atomic_write_parquet(products_path, pl.DataFrame())

    quarantine_path: Path | None = None
    if quarantine_records:
        quarantine_path = quarantine_run_dir(data_root, run_id) / "bronze_records.jsonl"
        atomic_write_jsonl(quarantine_path, quarantine_records)

    manifest_payload = {
        "schema_version": "1.0.0",
        "layer": "bronze",
        "source": "kurly",
        "batch_id": batch_id,
        "run_id": run_id,
        "code_version": code_version,
        "parser_version": parser_version,
        "input_manifest_checksum": manifest_checksum,
        "input_count": len(products),
        "valid_count": len(valid_records),
        "quarantine_count": len(quarantine_records),
        "products_parquet": "products.parquet",
        "products_checksum": parquet_checksum(products_path),
        "quarantine_path": quarantine_path.as_posix() if quarantine_path else None,
        "created_at": now_iso(),
    }
    manifest_out = staging / "manifest.json"
    atomic_write_json(manifest_out, manifest_payload)
    promote_staging(staging, batch_dir, ("products.parquet", "manifest.json"))

    final_manifest = batch_dir / "manifest.json"
    final_products = batch_dir / "products.parquet"
    return BronzeBatchResult(
        input_count=len(products),
        valid_count=len(valid_records),
        quarantine_count=len(quarantine_records),
        batch_dir=batch_dir,
        manifest_path=final_manifest,
        products_path=final_products,
        quarantine_path=quarantine_path,
    )
