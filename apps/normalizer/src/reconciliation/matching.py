from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..checksum import with_content_hash
from ..kurly_transform.text import clean_text

RECONCILE_RULE_VERSION = "kurly_kfia_reconcile_v1.0.0"
PAIR_SEPARATOR = "__"


@dataclass(frozen=True, slots=True)
class MatchOutcome:
    review_status: str
    match_type: str
    confidence: float
    rule_id: str
    selected_source: str
    mfds_record_id: str | None
    selected_expiration_text: str | None
    selected_storage_type: str | None
    candidate_kfia_record_ids: tuple[str, ...]
    evidence: dict[str, Any]


def make_reconcile_pair_id(kurly_batch_id: str, kfia_dataset_version: str) -> str:
    return f"{kurly_batch_id}{PAIR_SEPARATOR}{kfia_dataset_version}"


def parse_reconcile_pair_id(pair_id: str) -> tuple[str, str]:
    if PAIR_SEPARATOR not in pair_id:
        raise ValueError(
            "reconcile pair id must be '{kurly_batch}__{kfia_dataset}' format"
        )
    kurly_batch_id, kfia_dataset_version = pair_id.split(PAIR_SEPARATOR, 1)
    if not kurly_batch_id or not kfia_dataset_version:
        raise ValueError("reconcile pair id is incomplete")
    return kurly_batch_id, kfia_dataset_version


def normalize_match_text(value: str | None) -> str:
    return clean_text(value).casefold()


def reconciled_storage_type(storage_type: str | None) -> str | None:
    if storage_type is None:
        return None
    if storage_type == "AMBIENT":
        return "ROOM"
    return storage_type


def storage_types_compatible(kurly_storage: str | None, kfia_storage: str | None) -> bool:
    left = reconciled_storage_type(kurly_storage)
    right = reconciled_storage_type(kfia_storage)
    if left is None or right is None:
        return False
    return left == right


def _expiration_days(kurly_row: dict[str, Any]) -> float | None:
    unit = str(kurly_row.get("expiration_unit") or "").upper()
    value = kurly_row.get("expiration_value")
    if value is None or unit != "DAY":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _kfia_shelf_life_days(kfia_row: dict[str, Any]) -> float | None:
    unit = str(kfia_row.get("original_unit") or "").strip()
    value = kfia_row.get("reference_shelf_life_days")
    if value is None:
        return None
    if unit not in {"일", "DAY", "day"}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _expiration_aligned(kurly_row: dict[str, Any], kfia_row: dict[str, Any]) -> bool:
    kurly_days = _expiration_days(kurly_row)
    kfia_days = _kfia_shelf_life_days(kfia_row)
    if kurly_days is None or kfia_days is None:
        return False
    return kurly_days == kfia_days


def load_managed_mappings(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    mappings = payload.get("mappings") or []
    result: dict[str, str] = {}
    for item in mappings:
        if not isinstance(item, dict):
            continue
        kurly_id = str(item.get("kurly_record_id") or "").strip()
        kfia_id = str(item.get("kfia_record_id") or "").strip()
        if kurly_id and kfia_id:
            result[kurly_id] = kfia_id
    return result


def _candidate_rows(
    kurly_row: dict[str, Any], kfia_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    target = normalize_match_text(kurly_row.get("food_name_normalized"))
    if not target:
        return []
    candidates: list[dict[str, Any]] = []
    for row in kfia_rows:
        food_type = normalize_match_text(row.get("food_type"))
        if food_type and food_type == target:
            if storage_types_compatible(
                str(kurly_row.get("storage_type") or ""),
                str(row.get("storage_type") or ""),
            ):
                candidates.append(row)
    return candidates


def match_kurly_record(
    kurly_row: dict[str, Any],
    *,
    kfia_rows: list[dict[str, Any]],
    managed_mappings: dict[str, str],
) -> MatchOutcome:
    kurly_record_id = str(kurly_row.get("record_id") or "")
    kfia_by_id = {str(row.get("record_id")): row for row in kfia_rows}

    mapped_id = managed_mappings.get(kurly_record_id)
    if mapped_id and mapped_id in kfia_by_id:
        kfia_row = kfia_by_id[mapped_id]
        return MatchOutcome(
            review_status="APPROVED",
            match_type="MANAGED_MAPPING",
            confidence=1.0,
            rule_id="RECONCILE-001",
            selected_source="MANUAL",
            mfds_record_id=mapped_id,
            selected_expiration_text=kurly_row.get("expiration_text_raw"),
            selected_storage_type=reconciled_storage_type(
                str(kurly_row.get("storage_type") or "UNKNOWN")
            ),
            candidate_kfia_record_ids=(mapped_id,),
            evidence={
                "mapping_source": "managed_mapping_file",
                "kfia_reference_item_code": kfia_row.get("reference_item_code"),
            },
        )

    candidates = _candidate_rows(kurly_row, kfia_rows)
    candidate_ids = tuple(str(row.get("record_id") or "") for row in candidates)

    if not candidates:
        return MatchOutcome(
            review_status="REVIEW_REQUIRED",
            match_type="NO_REFERENCE",
            confidence=0.0,
            rule_id="RECONCILE-005",
            selected_source="NONE",
            mfds_record_id=None,
            selected_expiration_text=kurly_row.get("expiration_text_raw"),
            selected_storage_type=reconciled_storage_type(
                str(kurly_row.get("storage_type") or "UNKNOWN")
            ),
            candidate_kfia_record_ids=(),
            evidence={"reason": "no exact food_type match with compatible storage"},
        )

    if len(candidates) > 1:
        return MatchOutcome(
            review_status="REVIEW_REQUIRED",
            match_type="MULTI_CANDIDATE",
            confidence=0.5,
            rule_id="RECONCILE-003",
            selected_source="NONE",
            mfds_record_id=None,
            selected_expiration_text=kurly_row.get("expiration_text_raw"),
            selected_storage_type=reconciled_storage_type(
                str(kurly_row.get("storage_type") or "UNKNOWN")
            ),
            candidate_kfia_record_ids=candidate_ids,
            evidence={
                "candidate_count": len(candidates),
                "candidate_reference_item_codes": [
                    row.get("reference_item_code") for row in candidates
                ],
            },
        )

    kfia_row = candidates[0]
    kfia_record_id = str(kfia_row.get("record_id") or "")
    if _expiration_aligned(kurly_row, kfia_row):
        return MatchOutcome(
            review_status="APPROVED",
            match_type="EXACT_NAME_UNIQUE",
            confidence=1.0,
            rule_id="RECONCILE-002",
            selected_source="KURLY",
            mfds_record_id=kfia_record_id,
            selected_expiration_text=kurly_row.get("expiration_text_raw"),
            selected_storage_type=reconciled_storage_type(
                str(kurly_row.get("storage_type") or "UNKNOWN")
            ),
            candidate_kfia_record_ids=(kfia_record_id,),
            evidence={
                "kfia_reference_item_code": kfia_row.get("reference_item_code"),
                "expiration_aligned": True,
            },
        )

    return MatchOutcome(
        review_status="REVIEW_REQUIRED",
        match_type="EXACT_NAME_EXPIRATION_MISMATCH",
        confidence=0.75,
        rule_id="RECONCILE-004",
        selected_source="NONE",
        mfds_record_id=kfia_record_id,
        selected_expiration_text=kurly_row.get("expiration_text_raw"),
        selected_storage_type=reconciled_storage_type(
            str(kurly_row.get("storage_type") or "UNKNOWN")
        ),
        candidate_kfia_record_ids=(kfia_record_id,),
        evidence={
            "kfia_reference_item_code": kfia_row.get("reference_item_code"),
            "kurly_expiration_days": _expiration_days(kurly_row),
            "kfia_reference_shelf_life_days": _kfia_shelf_life_days(kfia_row),
        },
    )


def build_reconciled_record(
    *,
    kurly_row: dict[str, Any],
    outcome: MatchOutcome,
    pair_id: str,
    run_id: str,
    parser_version: str,
    created_at: str,
    mfds_expiration_text: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "batch_id": pair_id,
        "record_id": str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{pair_id}:{kurly_row.get('record_id')}:{outcome.match_type}",
            )
        ),
        "source": "RECONCILER",
        "source_record_id": str(kurly_row.get("record_id")),
        "parser_version": parser_version,
        "created_at": created_at,
        "kurly_record_id": str(kurly_row.get("record_id")),
        "mfds_record_id": outcome.mfds_record_id,
        "review_status": outcome.review_status,
        "match_type": outcome.match_type,
        "confidence": outcome.confidence,
        "rule_id": outcome.rule_id,
        "rule_version": RECONCILE_RULE_VERSION,
        "selected_source": outcome.selected_source,
        "kurly_expiration_text": kurly_row.get("expiration_text_raw"),
        "mfds_expiration_text": mfds_expiration_text,
        "selected_expiration_text": outcome.selected_expiration_text,
        "selected_storage_type": outcome.selected_storage_type,
    }
    return with_content_hash(payload)
