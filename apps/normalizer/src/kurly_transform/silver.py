from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from ..checksum import with_content_hash
from ..contracts import validate_payload
from ..storage_paths import bronze_batch_dir, silver_batch_dir
from .common import (
    atomic_write_json,
    atomic_write_jsonl,
    atomic_write_parquet,
    now_iso,
    parquet_checksum,
    promote_staging,
    staging_dir,
)
from .text import (
    ExpirationParseResult,
    clean_text,
    normalize_storage_type,
    parse_expiration,
)

SILVER_RULE_VERSION = "kurly_silver_v1.0.0"
REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(slots=True)
class SilverBatchResult:
    input_count: int
    unique_product_count: int
    parse_success_count: int
    review_required_count: int
    evidence_preservation_rate: float
    batch_dir: Path
    manifest_path: Path
    products_path: Path
    evidence_path: Path
    review_csv_path: Path


def _bronze_manifest_path(data_root: Path, batch_id: str) -> Path:
    return bronze_batch_dir(data_root, "kurly", batch_id) / "manifest.json"


def _select_representative(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def sort_key(row: dict[str, Any]) -> tuple[float, str]:
        confidence = row.get("ocr_confidence")
        numeric = float(confidence) if confidence is not None and confidence != "" else -1.0
        created_at = str(row.get("created_at") or "")
        return (-numeric, created_at)

    return sorted(rows, key=sort_key)[0]


def _collect_expiration_candidates(row: dict[str, Any]) -> list[tuple[str, str | None]]:
    candidates: list[tuple[str, str | None]] = []
    dom = row.get("expiration_info_dom")
    if dom:
        candidates.append(("DOM", str(dom)))
    raw = row.get("expiration_info_raw")
    if raw:
        source = str(row.get("expiration_source") or "OCR").upper()
        candidates.append((source, str(raw)))
    return candidates


def _choose_expiration(
    row: dict[str, Any],
) -> tuple[ExpirationParseResult, str | None, str | None]:
    candidates = _collect_expiration_candidates(row)
    if not candidates:
        return ExpirationParseResult(None, None, None, True), None, None

    for source, text in candidates:
        parsed = parse_expiration(text)
        if parsed.value is not None:
            return parsed, text, source
    first_source, first_text = candidates[0]
    return parse_expiration(first_text), first_text, first_source


def _build_silver_record(
    *,
    row: dict[str, Any],
    batch_id: str,
    run_id: str,
    parser_version: str,
    duplicate_count: int,
    group_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    food_name = clean_text(row.get("food_name_candidate")) or clean_text(
        row.get("product_name_raw")
    )
    review_required = not food_name
    if not food_name:
        food_name = clean_text(row.get("product_name_raw")) or "UNKNOWN"

    storage_type, storage_review = normalize_storage_type(
        storage_type_dom=row.get("storage_type_dom"),
        storage_method_dom=row.get("storage_method_dom"),
        storage_type_raw=row.get("storage_type"),
        storage_method_raw=row.get("storage_method_raw"),
    )
    expiration, expiration_text, expiration_source = _choose_expiration(row)
    review_required = (
        review_required
        or storage_review
        or expiration.review_required
        or expiration.value is None
    )

    silver_payload = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "batch_id": batch_id,
        "record_id": str(row.get("record_id")),
        "source": "KURLY",
        "source_record_id": str(row.get("source_record_id")),
        "source_uri": row.get("product_url"),
        "parser_version": parser_version,
        "created_at": row.get("created_at") or now_iso(),
        "food_name_normalized": food_name,
        "storage_type": storage_type,
        "expiration_value": expiration.value,
        "expiration_unit": expiration.unit,
        "expiration_basis": expiration.basis,
        "expiration_text_raw": expiration_text,
    }
    silver_payload = with_content_hash(silver_payload)

    evidence = {
        "original_product_id": str(row.get("original_product_id")),
        "batch_id": batch_id,
        "duplicate_count": duplicate_count,
        "selected_record_id": row.get("record_id"),
        "selection_rule": "HIGHEST_OCR_CONFIDENCE_THEN_EARLIEST_CREATED_AT",
        "selection_rule_version": SILVER_RULE_VERSION,
        "review_status": REVIEW_REQUIRED if review_required else "OK",
        "dom_expiration": row.get("expiration_info_dom"),
        "ocr_expiration": row.get("expiration_info_raw"),
        "dom_storage_method": row.get("storage_method_dom"),
        "ocr_storage_method": row.get("storage_method_raw"),
        "dom_storage_type": row.get("storage_type_dom"),
        "ocr_storage_type": row.get("storage_type"),
        "selected_expiration_source": expiration_source,
        "selected_storage_type": storage_type,
        "ocr_confidence": row.get("ocr_confidence"),
        "group_record_ids": [item.get("record_id") for item in group_rows],
    }
    parse_success = not review_required
    return silver_payload, evidence, parse_success


def run_kurly_silver(
    *,
    data_root: Path,
    batch_id: str,
    run_id: str,
    code_version: str,
    attempt: int,
) -> SilverBatchResult:
    bronze_manifest_path = _bronze_manifest_path(data_root, batch_id)
    if not bronze_manifest_path.is_file():
        raise FileNotFoundError(f"bronze manifest not found: {bronze_manifest_path}")

    bronze_manifest = json.loads(bronze_manifest_path.read_text(encoding="utf-8"))
    if int(bronze_manifest.get("valid_count") or 0) <= 0:
        raise ValueError("bronze manifest has no valid records")

    bronze_products_path = bronze_batch_dir(data_root, "kurly", batch_id) / "products.parquet"
    if not bronze_products_path.is_file():
        raise FileNotFoundError(f"bronze products not found: {bronze_products_path}")

    frame = pl.read_parquet(bronze_products_path)
    rows = frame.to_dicts()
    parser_version = str(bronze_manifest.get("parser_version") or code_version)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        product_id = str(row.get("original_product_id") or "")
        grouped.setdefault(product_id, []).append(row)

    silver_records: list[dict[str, Any]] = []
    evidence_records: list[dict[str, Any]] = []
    review_rows: list[dict[str, str]] = []
    parse_success_count = 0
    review_required_count = 0
    evidence_preserved = 0

    for product_id, group_rows in sorted(grouped.items(), key=lambda item: item[0]):
        representative = _select_representative(group_rows)
        silver_record, evidence, parse_success = _build_silver_record(
            row=representative,
            batch_id=batch_id,
            run_id=run_id,
            parser_version=parser_version,
            duplicate_count=len(group_rows),
            group_rows=group_rows,
        )
        validation = validate_payload("normalized_freshness", silver_record)
        if not validation.ok:
            raise ValueError(
                f"silver record failed contract validation for {product_id}: "
                + validation.issues[0].message
            )
        silver_records.append(silver_record)
        evidence_records.append(evidence)
        if parse_success:
            parse_success_count += 1
        else:
            review_required_count += 1
        if evidence.get("dom_expiration") or evidence.get("ocr_expiration"):
            evidence_preserved += 1
        review_rows.append(
            {
                "original_product_id": product_id,
                "food_name_normalized": silver_record["food_name_normalized"],
                "storage_type": silver_record["storage_type"],
                "expiration_text_raw": silver_record.get("expiration_text_raw") or "",
                "review_status": evidence["review_status"],
                "duplicate_count": str(len(group_rows)),
            }
        )

    batch_dir = silver_batch_dir(data_root, "kurly", batch_id)
    staging = staging_dir(batch_dir, attempt)
    staging.mkdir(parents=True, exist_ok=True)

    products_path = staging / "products.parquet"
    evidence_path = staging / "evidence.jsonl"
    review_csv_path = staging / "review.csv"
    atomic_write_parquet(products_path, pl.DataFrame(silver_records))
    atomic_write_jsonl(evidence_path, evidence_records)
    review_frame = pl.DataFrame(review_rows) if review_rows else pl.DataFrame(
        schema={
            "original_product_id": pl.Utf8,
            "food_name_normalized": pl.Utf8,
            "storage_type": pl.Utf8,
            "expiration_text_raw": pl.Utf8,
            "review_status": pl.Utf8,
            "duplicate_count": pl.Utf8,
        }
    )
    review_csv_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_csv = review_csv_path.with_name(f".{review_csv_path.name}.{uuid.uuid4().hex}.tmp")
    review_frame.write_csv(temporary_csv)
    temporary_csv.replace(review_csv_path)

    unique_count = len(silver_records)
    evidence_rate = (evidence_preserved / unique_count) if unique_count else 0.0
    manifest_payload = {
        "schema_version": "1.0.0",
        "layer": "silver",
        "source": "kurly",
        "batch_id": batch_id,
        "run_id": run_id,
        "code_version": code_version,
        "rule_version": SILVER_RULE_VERSION,
        "input_bronze_checksum": bronze_manifest.get("products_checksum"),
        "input_count": len(rows),
        "unique_product_count": unique_count,
        "parse_success_count": parse_success_count,
        "review_required_count": review_required_count,
        "evidence_preservation_rate": round(evidence_rate, 4),
        "products_parquet": "products.parquet",
        "products_checksum": parquet_checksum(products_path),
        "evidence_jsonl": "evidence.jsonl",
        "review_csv": "review.csv",
        "created_at": now_iso(),
    }
    manifest_out = staging / "manifest.json"
    atomic_write_json(manifest_out, manifest_payload)
    promote_staging(
        staging,
        batch_dir,
        ("products.parquet", "evidence.jsonl", "review.csv", "manifest.json"),
    )

    return SilverBatchResult(
        input_count=len(rows),
        unique_product_count=unique_count,
        parse_success_count=parse_success_count,
        review_required_count=review_required_count,
        evidence_preservation_rate=evidence_rate,
        batch_dir=batch_dir,
        manifest_path=batch_dir / "manifest.json",
        products_path=batch_dir / "products.parquet",
        evidence_path=batch_dir / "evidence.jsonl",
        review_csv_path=batch_dir / "review.csv",
    )
