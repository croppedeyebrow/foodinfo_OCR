from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from ..adapters.kfia_native_csv import (
    KfiaAdaptError,
    adapt_kfia_native_row,
    bronze_record_to_payload,
)
from ..contracts import validate_payload
from ..kfia_export_columns import EXPORT_FILENAME, read_native_export
from ..kurly_transform.common import (
    atomic_write_json,
    atomic_write_jsonl,
    atomic_write_parquet,
    now_iso,
    parquet_checksum,
    promote_staging,
    staging_dir,
)
from ..reference_registration import load_reference_manifest
from ..storage_paths import bronze_batch_dir, quarantine_run_dir, reference_inbox_dir


@dataclass(slots=True)
class KfiaBronzeBatchResult:
    input_count: int
    valid_count: int
    quarantine_count: int
    batch_dir: Path
    manifest_path: Path
    records_path: Path
    quarantine_path: Path | None


def run_kfia_bronze(
    *,
    data_root: Path,
    dataset_version: str,
    run_id: str,
    code_version: str,
    attempt: int,
) -> KfiaBronzeBatchResult:
    manifest = load_reference_manifest(data_root, dataset_version)
    if manifest is None:
        raise FileNotFoundError(
            f"reference manifest not found for dataset version {dataset_version}"
        )
    if str(manifest.get("status", "")).upper() not in {"REGISTERED", "VALIDATED"}:
        raise ValueError("reference manifest status must be REGISTERED or VALIDATED")

    export_path = reference_inbox_dir(data_root, dataset_version) / EXPORT_FILENAME
    if not export_path.is_file():
        raise FileNotFoundError(f"reference export not found: {export_path}")

    parser_version = str(manifest.get("parser_version") or code_version)
    frame = read_native_export(export_path)
    rows = frame.to_dicts()
    created_at = now_iso()
    valid_records: list[dict[str, Any]] = []
    quarantine_records: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        try:
            adapted = adapt_kfia_native_row(row)
            bronze_record = bronze_record_to_payload(
                adapted,
                dataset_version=dataset_version,
                run_id=run_id,
                parser_version=parser_version,
                created_at=created_at,
                source_row_index=index,
            )
        except KfiaAdaptError as error:
            quarantine_records.append(
                {
                    "index": index,
                    "reference_item_code": row.get("품목코드"),
                    "error_code": error.error_code,
                    "field": error.field,
                    "message": str(error),
                    "payload": row,
                }
            )
            continue
        validation = validate_payload("kfia_reference_bronze", bronze_record)
        if not validation.ok:
            quarantine_records.append(
                {
                    "index": index,
                    "reference_item_code": bronze_record.get("reference_item_code"),
                    "error_code": validation.issues[0].error_code,
                    "message": validation.issues[0].message,
                    "payload": bronze_record,
                }
            )
            continue
        valid_records.append(bronze_record)

    batch_dir = bronze_batch_dir(data_root, "kfia", dataset_version)
    staging = staging_dir(batch_dir, attempt)
    staging.mkdir(parents=True, exist_ok=True)

    records_path = staging / "records.parquet"
    atomic_write_parquet(
        records_path,
        pl.DataFrame(valid_records) if valid_records else pl.DataFrame(),
    )

    quarantine_path: Path | None = None
    if quarantine_records:
        quarantine_path = quarantine_run_dir(data_root, run_id) / "kfia_bronze_records.jsonl"
        atomic_write_jsonl(quarantine_path, quarantine_records)

    manifest_payload = {
        "schema_version": "1.0.0",
        "layer": "bronze",
        "source": "kfia",
        "batch_id": dataset_version,
        "dataset_version": dataset_version,
        "run_id": run_id,
        "code_version": code_version,
        "parser_version": parser_version,
        "input_export_checksum": manifest.get("export_checksum"),
        "input_count": len(rows),
        "valid_count": len(valid_records),
        "quarantine_count": len(quarantine_records),
        "records_parquet": "records.parquet",
        "records_checksum": parquet_checksum(records_path),
        "quarantine_path": quarantine_path.as_posix() if quarantine_path else None,
        "created_at": created_at,
    }
    manifest_out = staging / "manifest.json"
    atomic_write_json(manifest_out, manifest_payload)
    promote_staging(staging, batch_dir, ("records.parquet", "manifest.json"))

    return KfiaBronzeBatchResult(
        input_count=len(rows),
        valid_count=len(valid_records),
        quarantine_count=len(quarantine_records),
        batch_dir=batch_dir,
        manifest_path=batch_dir / "manifest.json",
        records_path=batch_dir / "records.parquet",
        quarantine_path=quarantine_path,
    )
