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
from ..reconciliation.matching import parse_reconcile_pair_id
from ..storage_paths import (
    gold_freshness_profiles_dir,
    reconciled_pair_dir,
    silver_batch_dir,
)
from .lineage import build_lineage_chain

GOLD_RULE_VERSION = "gold_freshness_v1.0.0"


class GoldDatasetVersionExistsError(ValueError):
    """Raised when a gold bundle already exists for the dataset version."""


@dataclass(slots=True)
class GoldPublishResult:
    dataset_version: str
    pair_id: str
    input_count: int
    approved_input_count: int
    excluded_count: int
    record_count: int
    lineage_linked_count: int
    batch_dir: Path
    manifest_path: Path
    records_path: Path
    csv_path: Path
    quality_summary_path: Path
    lineage_path: Path


def _load_kurly_evidence_by_silver_id(path: Path, silver_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    evidence_lines = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(evidence_lines) != len(silver_rows):
        by_product = {str(item.get("original_product_id")): item for item in evidence_lines}
        index: dict[str, dict[str, Any]] = {}
        for row in silver_rows:
            product_id = str(row.get("source_record_id") or "")
            evidence = by_product.get(product_id)
            if evidence is None:
                for candidate in evidence_lines:
                    if str(candidate.get("selected_record_id")) == str(row.get("source_record_id")):
                        evidence = candidate
                        break
            if evidence is not None:
                index[str(row.get("record_id"))] = evidence
        return index
    return {
        str(silver["record_id"]): evidence
        for silver, evidence in zip(silver_rows, evidence_lines, strict=True)
    }


def _expiration_fields(
    *,
    reconciled_row: dict[str, Any],
    kurly_row: dict[str, Any],
    kfia_row: dict[str, Any] | None,
) -> tuple[float | None, str | None, str | None]:
    selected_source = str(reconciled_row.get("selected_source") or "")
    if selected_source == "MFDS" and kfia_row is not None:
        unit_raw = str(kfia_row.get("original_unit") or "").strip()
        value = kfia_row.get("reference_shelf_life_days")
        if value is None:
            return None, None, None
        unit = "DAY" if unit_raw in {"일", "DAY", "day"} else None
        return float(value), unit, "UNKNOWN"
    return (
        kurly_row.get("expiration_value"),
        kurly_row.get("expiration_unit"),
        kurly_row.get("expiration_basis"),
    )


def _food_mapping_key(
    kurly_row: dict[str, Any],
    kfia_row: dict[str, Any] | None,
) -> str:
    if kfia_row is not None:
        return str(kfia_row.get("reference_item_code") or kurly_row.get("food_name_normalized"))
    return str(kurly_row.get("food_name_normalized") or "UNKNOWN")


def build_gold_record(
    *,
    reconciled_row: dict[str, Any],
    kurly_row: dict[str, Any],
    kurly_evidence: dict[str, Any],
    kfia_row: dict[str, Any] | None,
    pair_id: str,
    run_id: str,
    parser_version: str,
    created_at: str,
) -> dict[str, Any]:
    external_product_id = str(kurly_evidence.get("original_product_id") or kurly_row.get("source_record_id"))
    expiration_value, expiration_unit, expiration_basis = _expiration_fields(
        reconciled_row=reconciled_row,
        kurly_row=kurly_row,
        kfia_row=kfia_row,
    )
    selected_source = str(reconciled_row.get("selected_source") or "")
    if selected_source not in {"KURLY", "MFDS", "MANUAL"}:
        raise ValueError(
            f"cannot publish gold for selected_source={selected_source!r} "
            f"on reconciled {reconciled_row.get('record_id')}"
        )
    storage_type = str(reconciled_row.get("selected_storage_type") or kurly_row.get("storage_type") or "UNKNOWN")
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "batch_id": pair_id,
        "record_id": str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"gold:{pair_id}:{reconciled_row.get('record_id')}",
            )
        ),
        "source": "GOLD",
        "source_record_id": str(reconciled_row.get("record_id")),
        "parser_version": parser_version,
        "created_at": created_at,
        "dataset_version": pair_id,
        "external_product_id": external_product_id,
        "food_mapping_key": _food_mapping_key(kurly_row, kfia_row),
        "product_name": str(kurly_row.get("food_name_normalized") or "UNKNOWN"),
        "storage_type": storage_type,
        "expiration_value": expiration_value,
        "expiration_unit": expiration_unit,
        "expiration_basis": expiration_basis,
        "selected_source": selected_source,
        "confidence": float(reconciled_row.get("confidence") or 0.0),
        "review_status": "APPROVED",
    }
    return with_content_hash(payload)


def run_gold_freshness_publish(
    *,
    data_root: Path,
    pair_id: str,
    run_id: str,
    code_version: str,
    attempt: int,
) -> GoldPublishResult:
    kurly_batch_id, kfia_dataset_version = parse_reconcile_pair_id(pair_id)
    dataset_version = pair_id
    batch_dir = gold_freshness_profiles_dir(data_root, dataset_version)
    if batch_dir.is_dir() and (batch_dir / "manifest.json").is_file():
        raise GoldDatasetVersionExistsError(
            f"gold bundle already exists for dataset_version={dataset_version}"
        )

    reconcile_manifest_path = reconciled_pair_dir(data_root, pair_id) / "manifest.json"
    if not reconcile_manifest_path.is_file():
        raise FileNotFoundError(f"reconciled manifest not found: {reconcile_manifest_path}")
    reconcile_manifest = json.loads(reconcile_manifest_path.read_text(encoding="utf-8"))
    reconciled_path = reconciled_pair_dir(data_root, pair_id) / "records.parquet"
    if not reconciled_path.is_file():
        raise FileNotFoundError(f"reconciled records not found: {reconciled_path}")

    kurly_silver_path = silver_batch_dir(data_root, "kurly", kurly_batch_id) / "products.parquet"
    kurly_evidence_path = silver_batch_dir(data_root, "kurly", kurly_batch_id) / "evidence.jsonl"
    kfia_silver_path = silver_batch_dir(data_root, "kfia", kfia_dataset_version) / "records.parquet"
    if not kurly_silver_path.is_file():
        raise FileNotFoundError(f"kurly silver not found: {kurly_silver_path}")
    if not kfia_silver_path.is_file():
        raise FileNotFoundError(f"kfia silver not found: {kfia_silver_path}")

    reconciled_rows = pl.read_parquet(reconciled_path).to_dicts()
    kurly_rows = pl.read_parquet(kurly_silver_path).to_dicts()
    kurly_by_id = {str(row.get("record_id")): row for row in kurly_rows}
    kfia_by_id = {
        str(row.get("record_id")): row for row in pl.read_parquet(kfia_silver_path).to_dicts()
    }
    evidence_by_kurly_silver = _load_kurly_evidence_by_silver_id(kurly_evidence_path, kurly_rows)

    parser_version = str(reconcile_manifest.get("code_version") or code_version)
    created_at = now_iso()

    gold_records: list[dict[str, Any]] = []
    lineage_records: list[dict[str, Any]] = []
    excluded_count = 0
    lineage_linked_count = 0

    for reconciled_row in reconciled_rows:
        if str(reconciled_row.get("review_status")) != "APPROVED":
            excluded_count += 1
            continue
        kurly_record_id = str(reconciled_row.get("kurly_record_id") or "")
        kurly_row = kurly_by_id.get(kurly_record_id)
        if kurly_row is None:
            excluded_count += 1
            continue
        kfia_record_id = reconciled_row.get("mfds_record_id")
        kfia_row = kfia_by_id.get(str(kfia_record_id)) if kfia_record_id else None
        kurly_evidence = evidence_by_kurly_silver.get(kurly_record_id, {})

        gold_record = build_gold_record(
            reconciled_row=reconciled_row,
            kurly_row=kurly_row,
            kurly_evidence=kurly_evidence,
            kfia_row=kfia_row,
            pair_id=pair_id,
            run_id=run_id,
            parser_version=parser_version,
            created_at=created_at,
        )
        validation = validate_payload("gold_freshness", gold_record)
        if not validation.ok:
            raise ValueError(
                f"gold record failed contract validation for {reconciled_row.get('record_id')}: "
                f"{validation.issues[0].message}"
            )
        gold_records.append(gold_record)

        kurly_bronze_record_id = str(
            kurly_evidence.get("selected_record_id") or kurly_row.get("source_record_id") or ""
        )
        kfia_bronze_record_id = (
            str(kfia_row.get("source_record_id")) if kfia_row is not None else None
        )
        lineage = build_lineage_chain(
            gold_record_id=str(gold_record["record_id"]),
            external_product_id=str(gold_record["external_product_id"]),
            pair_id=pair_id,
            kurly_batch_id=kurly_batch_id,
            kfia_dataset_version=kfia_dataset_version,
            reconciled_record_id=str(reconciled_row.get("record_id")),
            kurly_silver_record_id=kurly_record_id,
            kurly_bronze_record_id=kurly_bronze_record_id or None,
            kfia_silver_record_id=str(kfia_record_id) if kfia_record_id else None,
            kfia_bronze_record_id=kfia_bronze_record_id,
        )
        lineage_records.append(lineage)
        if lineage["lineage_complete"]:
            lineage_linked_count += 1

    staging = staging_dir(batch_dir, attempt)
    staging.mkdir(parents=True, exist_ok=True)

    records_path = staging / "freshness_profiles.parquet"
    csv_path = staging / "freshness_profiles.csv"
    lineage_path = staging / "lineage.jsonl"
    quality_summary_path = staging / "quality_summary.json"

    frame = pl.DataFrame(gold_records) if gold_records else pl.DataFrame()
    atomic_write_parquet(records_path, frame)
    temporary_csv = csv_path.with_name(f".{csv_path.name}.{uuid.uuid4().hex}.tmp")
    frame.write_csv(temporary_csv)
    temporary_csv.replace(csv_path)
    atomic_write_jsonl(lineage_path, lineage_records)

    input_count = len(reconciled_rows)
    approved_input_count = len(gold_records)
    matching_rate = (
        float(reconcile_manifest.get("approved_count") or 0) / input_count if input_count else 0.0
    )
    quality_summary = {
        "schema_version": "1.0.0",
        "dataset_version": dataset_version,
        "pair_id": pair_id,
        "kurly_batch_id": kurly_batch_id,
        "kfia_dataset_version": kfia_dataset_version,
        "input_reconciled_count": input_count,
        "approved_input_count": approved_input_count,
        "excluded_count": excluded_count,
        "gold_record_count": approved_input_count,
        "matching_rate": matching_rate,
        "lineage_linked_count": lineage_linked_count,
        "lineage_link_rate": (
            lineage_linked_count / approved_input_count if approved_input_count else 0.0
        ),
        "reconcile_rule_version": reconcile_manifest.get("rule_version"),
        "gold_rule_version": GOLD_RULE_VERSION,
        "created_at": created_at,
    }
    atomic_write_json(quality_summary_path, quality_summary)

    manifest_payload = {
        "schema_version": "1.0.0",
        "layer": "gold",
        "dataset": "freshness_profiles",
        "dataset_version": dataset_version,
        "pair_id": pair_id,
        "kurly_batch_id": kurly_batch_id,
        "kfia_dataset_version": kfia_dataset_version,
        "run_id": run_id,
        "code_version": code_version,
        "rule_version": GOLD_RULE_VERSION,
        "input_reconciled_checksum": reconcile_manifest.get("records_checksum"),
        "input_reconciled_count": input_count,
        "approved_input_count": approved_input_count,
        "excluded_count": excluded_count,
        "record_count": approved_input_count,
        "lineage_linked_count": lineage_linked_count,
        "freshness_profiles_parquet": "freshness_profiles.parquet",
        "freshness_profiles_checksum": parquet_checksum(records_path) if gold_records else None,
        "freshness_profiles_csv": "freshness_profiles.csv",
        "quality_summary_json": "quality_summary.json",
        "lineage_jsonl": "lineage.jsonl",
        "created_at": created_at,
    }
    manifest_out = staging / "manifest.json"
    atomic_write_json(manifest_out, manifest_payload)
    promote_staging(
        staging,
        batch_dir,
        (
            "freshness_profiles.parquet",
            "freshness_profiles.csv",
            "quality_summary.json",
            "lineage.jsonl",
            "manifest.json",
        ),
    )

    return GoldPublishResult(
        dataset_version=dataset_version,
        pair_id=pair_id,
        input_count=input_count,
        approved_input_count=approved_input_count,
        excluded_count=excluded_count,
        record_count=approved_input_count,
        lineage_linked_count=lineage_linked_count,
        batch_dir=batch_dir,
        manifest_path=batch_dir / "manifest.json",
        records_path=batch_dir / "freshness_profiles.parquet",
        csv_path=batch_dir / "freshness_profiles.csv",
        quality_summary_path=batch_dir / "quality_summary.json",
        lineage_path=batch_dir / "lineage.jsonl",
    )
