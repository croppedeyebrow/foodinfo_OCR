from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..reconciliation.matching import parse_reconcile_pair_id
from ..storage_paths import (
    accepted_inbox_dir,
    bronze_batch_dir,
    gold_freshness_profiles_dir,
    reconciled_pair_dir,
    silver_batch_dir,
)


def _manifest_count(path: Path, *keys: str) -> int | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return int(value)
    return None


def build_results_summary(data_root: Path, pair_id: str) -> dict[str, Any]:
    kurly_batch_id, kfia_dataset_version = parse_reconcile_pair_id(pair_id)

    accepted_manifest = accepted_inbox_dir(data_root, kurly_batch_id) / "manifest.json"
    kurly_bronze_manifest = bronze_batch_dir(data_root, "kurly", kurly_batch_id) / "manifest.json"
    kurly_silver_manifest = silver_batch_dir(data_root, "kurly", kurly_batch_id) / "manifest.json"
    kfia_bronze_manifest = bronze_batch_dir(data_root, "kfia", kfia_dataset_version) / "manifest.json"
    kfia_silver_manifest = silver_batch_dir(data_root, "kfia", kfia_dataset_version) / "manifest.json"
    reconciled_manifest = reconciled_pair_dir(data_root, pair_id) / "manifest.json"
    gold_manifest = gold_freshness_profiles_dir(data_root, pair_id) / "manifest.json"
    quality_summary_path = gold_freshness_profiles_dir(data_root, pair_id) / "quality_summary.json"

    layer_counts = {
        "accepted": _manifest_count(accepted_manifest, "row_count", "accepted_count"),
        "kurly_bronze": _manifest_count(kurly_bronze_manifest, "valid_count", "record_count"),
        "kurly_silver": _manifest_count(
            kurly_silver_manifest, "unique_product_count", "record_count"
        ),
        "kfia_bronze": _manifest_count(kfia_bronze_manifest, "valid_count", "record_count"),
        "kfia_silver": _manifest_count(kfia_silver_manifest, "record_count"),
        "reconciled": _manifest_count(reconciled_manifest, "record_count", "input_count"),
        "gold": _manifest_count(gold_manifest, "record_count", "approved_input_count"),
        "quarantine_kurly": _manifest_count(
            kurly_bronze_manifest, "quarantine_count"
        ),
        "quarantine_kfia": _manifest_count(kfia_bronze_manifest, "quarantine_count"),
    }

    quality_summary: dict[str, Any] | None = None
    if quality_summary_path.is_file():
        quality_summary = json.loads(quality_summary_path.read_text(encoding="utf-8"))

    reconcile_summary: dict[str, Any] | None = None
    if reconciled_manifest.is_file():
        reconcile_summary = json.loads(reconciled_manifest.read_text(encoding="utf-8"))

    gold_summary: dict[str, Any] | None = None
    if gold_manifest.is_file():
        gold_summary = json.loads(gold_manifest.read_text(encoding="utf-8"))

    return {
        "pair_id": pair_id,
        "kurly_batch_id": kurly_batch_id,
        "kfia_dataset_version": kfia_dataset_version,
        "layer_counts": layer_counts,
        "reconcile_summary": reconcile_summary,
        "gold_summary": gold_summary,
        "quality_summary": quality_summary,
        "has_gold": gold_manifest.is_file(),
    }


def load_lineage_for_gold_record(
    data_root: Path, pair_id: str, gold_record_id: str
) -> dict[str, Any] | None:
    lineage_path = gold_freshness_profiles_dir(data_root, pair_id) / "lineage.jsonl"
    if not lineage_path.is_file():
        return None
    for line in lineage_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if str(payload.get("gold_record_id")) == gold_record_id:
            return payload
    return None
