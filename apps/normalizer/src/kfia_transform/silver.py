from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from ..checksum import with_content_hash
from ..contracts import validate_payload
from ..kurly_transform.common import (
    atomic_write_json,
    atomic_write_jsonl,
    atomic_write_parquet,
    now_iso,
    parquet_checksum,
    promote_staging,
    staging_dir,
)
from ..quality.kfia_rules import (
    QUALITY_RULE_VERSION,
    evaluate_kfia_quality,
    normalize_kfia_storage_type,
    summarize_quality_counts,
)
from ..storage_paths import bronze_batch_dir, silver_batch_dir

SILVER_RULE_VERSION = "kfia_silver_v1.0.0"


@dataclass(slots=True)
class KfiaSilverBatchResult:
    input_count: int
    record_count: int
    approved_count: int
    review_required_count: int
    rejected_count: int
    batch_dir: Path
    manifest_path: Path
    records_path: Path
    evidence_path: Path
    review_csv_path: Path


def _bronze_manifest_path(data_root: Path, dataset_version: str) -> Path:
    return bronze_batch_dir(data_root, "kfia", dataset_version) / "manifest.json"


def _build_silver_record(
    *,
    row: dict[str, Any],
    dataset_version: str,
    run_id: str,
    parser_version: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    storage_type_raw = str(row.get("storage_type_raw") or "")
    storage_type, _storage_review = normalize_kfia_storage_type(storage_type_raw)
    review_status, findings = evaluate_kfia_quality(row)

    silver_payload = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "batch_id": dataset_version,
        "record_id": str(row.get("record_id")),
        "source": "KFIA",
        "source_record_id": str(row.get("source_record_id")),
        "parser_version": parser_version,
        "created_at": row.get("created_at") or now_iso(),
        "reference_item_code": str(row.get("reference_item_code")),
        "food_type": row.get("food_type"),
        "food_name": row.get("food_name"),
        "storage_type_raw": storage_type_raw,
        "storage_type": storage_type,
        "reference_temperature_raw": row.get("reference_temperature_raw"),
        "reference_shelf_life_days": float(row.get("reference_shelf_life_days")),
        "original_unit": str(row.get("original_unit")),
        "source_document": str(row.get("source_document")),
        "source_page": int(row.get("source_page")),
        "review_status": review_status,
        "quality_rule_version": QUALITY_RULE_VERSION,
        "quality_findings": [
            {"rule_id": item.rule_id, "severity": item.severity, "message": item.message}
            for item in findings
        ],
    }
    silver_payload = with_content_hash(silver_payload)

    evidence = {
        "dataset_version": dataset_version,
        "reference_item_code": row.get("reference_item_code"),
        "food_type": row.get("food_type"),
        "food_name": row.get("food_name"),
        "safety_factor": row.get("safety_factor"),
        "safety_factor_raw": row.get("safety_factor_raw"),
        "temperature_details": row.get("temperature_details"),
        "raw_payload": row.get("raw_payload"),
        "review_status": review_status,
        "quality_findings": silver_payload["quality_findings"],
        "selection_rule_version": SILVER_RULE_VERSION,
    }
    return silver_payload, evidence


def run_kfia_silver(
    *,
    data_root: Path,
    dataset_version: str,
    run_id: str,
    code_version: str,
    attempt: int,
) -> KfiaSilverBatchResult:
    bronze_manifest_path = _bronze_manifest_path(data_root, dataset_version)
    if not bronze_manifest_path.is_file():
        raise FileNotFoundError(f"kfia bronze manifest not found: {bronze_manifest_path}")

    bronze_manifest = json.loads(bronze_manifest_path.read_text(encoding="utf-8"))
    if int(bronze_manifest.get("valid_count") or 0) <= 0:
        raise ValueError("kfia bronze manifest has no valid records")

    bronze_records_path = bronze_batch_dir(data_root, "kfia", dataset_version) / "records.parquet"
    if not bronze_records_path.is_file():
        raise FileNotFoundError(f"kfia bronze records not found: {bronze_records_path}")

    frame = pl.read_parquet(bronze_records_path)
    rows = frame.to_dicts()
    parser_version = str(bronze_manifest.get("parser_version") or code_version)

    silver_records: list[dict[str, Any]] = []
    evidence_records: list[dict[str, Any]] = []
    review_rows: list[dict[str, str]] = []
    statuses: list[str] = []

    for row in rows:
        silver_record, evidence = _build_silver_record(
            row=row,
            dataset_version=dataset_version,
            run_id=run_id,
            parser_version=parser_version,
        )
        validation = validate_payload("kfia_reference_silver", silver_record)
        if not validation.ok:
            raise ValueError(
                f"silver record failed contract validation for {row.get('record_id')}: "
                + validation.issues[0].message
            )
        silver_records.append(silver_record)
        evidence_records.append(evidence)
        statuses.append(str(silver_record["review_status"]))
        review_rows.append(
            {
                "reference_item_code": silver_record["reference_item_code"],
                "food_type": str(silver_record.get("food_type") or ""),
                "storage_type": silver_record["storage_type"],
                "reference_shelf_life_days": str(silver_record["reference_shelf_life_days"]),
                "review_status": silver_record["review_status"],
                "source_document": silver_record["source_document"],
                "source_page": str(silver_record["source_page"]),
            }
        )

    quality_summary = summarize_quality_counts(statuses)  # type: ignore[arg-type]

    batch_dir = silver_batch_dir(data_root, "kfia", dataset_version)
    staging = staging_dir(batch_dir, attempt)
    staging.mkdir(parents=True, exist_ok=True)

    records_path = staging / "records.parquet"
    evidence_path = staging / "evidence.jsonl"
    review_csv_path = staging / "review.csv"
    atomic_write_parquet(records_path, pl.DataFrame(silver_records))
    atomic_write_jsonl(evidence_path, evidence_records)
    review_frame = pl.DataFrame(review_rows) if review_rows else pl.DataFrame()
    temporary_csv = review_csv_path.with_name(f".{review_csv_path.name}.{uuid.uuid4().hex}.tmp")
    review_frame.write_csv(temporary_csv)
    temporary_csv.replace(review_csv_path)

    record_count = len(silver_records)
    manifest_payload = {
        "schema_version": "1.0.0",
        "layer": "silver",
        "source": "kfia",
        "batch_id": dataset_version,
        "dataset_version": dataset_version,
        "run_id": run_id,
        "code_version": code_version,
        "rule_version": SILVER_RULE_VERSION,
        "quality_rule_version": QUALITY_RULE_VERSION,
        "input_bronze_checksum": bronze_manifest.get("records_checksum"),
        "input_count": len(rows),
        "record_count": record_count,
        "approved_count": quality_summary["approved_count"],
        "review_required_count": quality_summary["review_required_count"],
        "rejected_count": quality_summary["rejected_count"],
        "records_parquet": "records.parquet",
        "records_checksum": parquet_checksum(records_path),
        "evidence_jsonl": "evidence.jsonl",
        "review_csv": "review.csv",
        "created_at": now_iso(),
    }
    manifest_out = staging / "manifest.json"
    atomic_write_json(manifest_out, manifest_payload)
    promote_staging(
        staging,
        batch_dir,
        ("records.parquet", "evidence.jsonl", "review.csv", "manifest.json"),
    )

    return KfiaSilverBatchResult(
        input_count=len(rows),
        record_count=record_count,
        approved_count=quality_summary["approved_count"],
        review_required_count=quality_summary["review_required_count"],
        rejected_count=quality_summary["rejected_count"],
        batch_dir=batch_dir,
        manifest_path=batch_dir / "manifest.json",
        records_path=batch_dir / "records.parquet",
        evidence_path=batch_dir / "evidence.jsonl",
        review_csv_path=batch_dir / "review.csv",
    )
