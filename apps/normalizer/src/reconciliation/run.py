from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

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
from ..storage_paths import reconciled_pair_dir, silver_batch_dir
from .matching import (
    RECONCILE_RULE_VERSION,
    build_reconciled_record,
    load_managed_mappings,
    match_kurly_record,
    parse_reconcile_pair_id,
)

MANAGED_MAPPING_RELATIVE = Path("mappings") / "default.json"


@dataclass(slots=True)
class ReconcileBatchResult:
    pair_id: str
    kurly_batch_id: str
    kfia_dataset_version: str
    input_count: int
    record_count: int
    approved_count: int
    review_required_count: int
    rejected_count: int
    no_reference_count: int
    batch_dir: Path
    manifest_path: Path
    records_path: Path
    evidence_path: Path
    review_csv_path: Path
    decisions_path: Path


def _managed_mapping_path(data_root: Path) -> Path:
    return data_root / MANAGED_MAPPING_RELATIVE


def _silver_manifest_path(data_root: Path, source: str, batch_id: str) -> Path:
    return silver_batch_dir(data_root, source, batch_id) / "manifest.json"


def _silver_records_path(data_root: Path, source: str, batch_id: str) -> Path:
    if source == "kurly":
        return silver_batch_dir(data_root, source, batch_id) / "products.parquet"
    return silver_batch_dir(data_root, source, batch_id) / "records.parquet"


def _kfia_expiration_text(row: dict[str, Any]) -> str | None:
    days = row.get("reference_shelf_life_days")
    unit = str(row.get("original_unit") or "").strip()
    if days is None:
        return None
    return f"{days}{unit}"


def run_kurly_kfia_reconcile(
    *,
    data_root: Path,
    pair_id: str,
    run_id: str,
    code_version: str,
    attempt: int,
) -> ReconcileBatchResult:
    kurly_batch_id, kfia_dataset_version = parse_reconcile_pair_id(pair_id)

    kurly_manifest_path = _silver_manifest_path(data_root, "kurly", kurly_batch_id)
    kfia_manifest_path = _silver_manifest_path(data_root, "kfia", kfia_dataset_version)
    if not kurly_manifest_path.is_file():
        raise FileNotFoundError(f"kurly silver manifest not found: {kurly_manifest_path}")
    if not kfia_manifest_path.is_file():
        raise FileNotFoundError(f"kfia silver manifest not found: {kfia_manifest_path}")

    kurly_manifest = json.loads(kurly_manifest_path.read_text(encoding="utf-8"))
    kfia_manifest = json.loads(kfia_manifest_path.read_text(encoding="utf-8"))

    kurly_records_path = _silver_records_path(data_root, "kurly", kurly_batch_id)
    kfia_records_path = _silver_records_path(data_root, "kfia", kfia_dataset_version)
    if not kurly_records_path.is_file():
        raise FileNotFoundError(f"kurly silver records not found: {kurly_records_path}")
    if not kfia_records_path.is_file():
        raise FileNotFoundError(f"kfia silver records not found: {kfia_records_path}")

    kurly_rows = pl.read_parquet(kurly_records_path).to_dicts()
    kfia_rows = pl.read_parquet(kfia_records_path).to_dicts()
    kfia_by_id = {str(row.get("record_id")): row for row in kfia_rows}
    managed_mappings = load_managed_mappings(_managed_mapping_path(data_root))
    parser_version = str(kurly_manifest.get("code_version") or code_version)
    created_at = now_iso()

    reconciled_records: list[dict[str, Any]] = []
    evidence_records: list[dict[str, Any]] = []
    review_rows: list[dict[str, str]] = []

    approved_count = 0
    review_required_count = 0
    rejected_count = 0
    no_reference_count = 0

    for kurly_row in kurly_rows:
        outcome = match_kurly_record(
            kurly_row,
            kfia_rows=kfia_rows,
            managed_mappings=managed_mappings,
        )
        kfia_row = (
            kfia_by_id.get(outcome.mfds_record_id or "")
            if outcome.mfds_record_id
            else None
        )
        reconciled = build_reconciled_record(
            kurly_row=kurly_row,
            outcome=outcome,
            pair_id=pair_id,
            run_id=run_id,
            parser_version=parser_version,
            created_at=created_at,
            mfds_expiration_text=(
                _kfia_expiration_text(kfia_row) if kfia_row is not None else None
            ),
        )

        validation = validate_payload("reconciled_freshness", reconciled)
        if not validation.ok:
            raise ValueError(
                f"reconciled record failed contract validation for "
                f"{kurly_row.get('record_id')}: {validation.issues[0].message}"
            )

        reconciled_records.append(reconciled)
        evidence_records.append(
            {
                "pair_id": pair_id,
                "kurly_record_id": kurly_row.get("record_id"),
                "kfia_record_id": outcome.mfds_record_id,
                "match_type": outcome.match_type,
                "review_status": outcome.review_status,
                "rule_id": outcome.rule_id,
                "confidence": outcome.confidence,
                "candidate_kfia_record_ids": list(outcome.candidate_kfia_record_ids),
                "evidence": outcome.evidence,
            }
        )

        status = str(reconciled["review_status"])
        if status == "APPROVED":
            approved_count += 1
        elif status == "REJECTED":
            rejected_count += 1
        else:
            review_required_count += 1
        if outcome.match_type == "NO_REFERENCE":
            no_reference_count += 1

        if status != "APPROVED":
            review_rows.append(
                {
                    "reconciled_record_id": reconciled["record_id"],
                    "kurly_record_id": reconciled["kurly_record_id"],
                    "food_name_normalized": str(kurly_row.get("food_name_normalized") or ""),
                    "kurly_storage_type": str(kurly_row.get("storage_type") or ""),
                    "kurly_expiration_text": str(kurly_row.get("expiration_text_raw") or ""),
                    "match_type": outcome.match_type,
                    "review_status": status,
                    "rule_id": outcome.rule_id,
                    "confidence": str(outcome.confidence),
                    "candidate_kfia_record_ids": ",".join(outcome.candidate_kfia_record_ids),
                }
            )

    batch_dir = reconciled_pair_dir(data_root, pair_id)
    staging = staging_dir(batch_dir, attempt)
    staging.mkdir(parents=True, exist_ok=True)

    records_path = staging / "records.parquet"
    evidence_path = staging / "evidence.jsonl"
    review_csv_path = staging / "review.csv"
    decisions_path = batch_dir / "decisions.jsonl"
    if not decisions_path.is_file():
        decisions_path.parent.mkdir(parents=True, exist_ok=True)
        decisions_path.write_text("", encoding="utf-8")

    atomic_write_parquet(records_path, pl.DataFrame(reconciled_records))
    atomic_write_jsonl(evidence_path, evidence_records)
    review_frame = pl.DataFrame(review_rows) if review_rows else pl.DataFrame()
    temporary_csv = review_csv_path.with_name(f".{review_csv_path.name}.{uuid.uuid4().hex}.tmp")
    review_frame.write_csv(temporary_csv)
    temporary_csv.replace(review_csv_path)

    record_count = len(reconciled_records)
    manifest_payload = {
        "schema_version": "1.0.0",
        "layer": "reconciled",
        "pair_id": pair_id,
        "kurly_batch_id": kurly_batch_id,
        "kfia_dataset_version": kfia_dataset_version,
        "run_id": run_id,
        "code_version": code_version,
        "rule_version": RECONCILE_RULE_VERSION,
        "kurly_silver_checksum": kurly_manifest.get("products_checksum"),
        "kfia_silver_checksum": kfia_manifest.get("records_checksum"),
        "input_count": len(kurly_rows),
        "record_count": record_count,
        "approved_count": approved_count,
        "review_required_count": review_required_count,
        "rejected_count": rejected_count,
        "no_reference_count": no_reference_count,
        "records_parquet": "records.parquet",
        "records_checksum": parquet_checksum(records_path),
        "evidence_jsonl": "evidence.jsonl",
        "review_csv": "review.csv",
        "decisions_jsonl": "decisions.jsonl",
        "created_at": created_at,
    }
    manifest_out = staging / "manifest.json"
    atomic_write_json(manifest_out, manifest_payload)
    promote_staging(
        staging,
        batch_dir,
        ("records.parquet", "evidence.jsonl", "review.csv", "manifest.json"),
    )

    return ReconcileBatchResult(
        pair_id=pair_id,
        kurly_batch_id=kurly_batch_id,
        kfia_dataset_version=kfia_dataset_version,
        input_count=len(kurly_rows),
        record_count=record_count,
        approved_count=approved_count,
        review_required_count=review_required_count,
        rejected_count=rejected_count,
        no_reference_count=no_reference_count,
        batch_dir=batch_dir,
        manifest_path=batch_dir / "manifest.json",
        records_path=batch_dir / "records.parquet",
        evidence_path=batch_dir / "evidence.jsonl",
        review_csv_path=batch_dir / "review.csv",
        decisions_path=decisions_path,
    )


def append_review_decision(
    *,
    data_root: Path,
    pair_id: str,
    decision: dict[str, Any],
) -> Path:
    validation = validate_payload("review_decision", decision)
    if not validation.ok:
        raise ValueError(validation.issues[0].message)

    batch_dir = reconciled_pair_dir(data_root, pair_id)
    batch_dir.mkdir(parents=True, exist_ok=True)
    decisions_path = batch_dir / "decisions.jsonl"
    with decisions_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(decision, ensure_ascii=False) + "\n")
    return decisions_path
