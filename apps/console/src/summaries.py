from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

BATCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
MEMBER_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,64}$")


@dataclass(frozen=True)
class CsvSummary:
    path: Path
    exists: bool
    row_count: int
    note: str = ""


@dataclass(frozen=True)
class TextCheckSummary:
    path: Path
    exists: bool
    row_count: int
    has_text: int
    no_text: int
    unknown: int


def count_csv_rows(path: Path) -> CsvSummary:
    if not path.exists():
        return CsvSummary(path=path, exists=False, row_count=0, note="missing")
    if path.stat().st_size == 0:
        return CsvSummary(path=path, exists=True, row_count=0, note="empty")
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    return CsvSummary(path=path, exists=True, row_count=len(rows))


def summarize_text_checks(path: Path) -> TextCheckSummary:
    if not path.exists() or path.stat().st_size == 0:
        return TextCheckSummary(
            path=path,
            exists=path.exists(),
            row_count=0,
            has_text=0,
            no_text=0,
            unknown=0,
        )
    counts: Counter[str] = Counter()
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            presence = (row.get("text_presence") or "").strip().upper()
            if presence:
                counts[presence] += 1
    total = sum(counts.values())
    return TextCheckSummary(
        path=path,
        exists=True,
        row_count=total,
        has_text=counts.get("HAS_TEXT", 0),
        no_text=counts.get("NO_TEXT", 0),
        unknown=counts.get("UNKNOWN", 0),
    )


def list_discovery_batches(
    discovery_root: Path,
    *,
    member_filter: str | None = None,
    require_file: str | None = None,
) -> list[str]:
    if not discovery_root.exists():
        return []
    batches: list[str] = []
    for path in sorted(discovery_root.iterdir(), key=lambda p: p.name, reverse=True):
        if not path.is_dir():
            continue
        name = path.name
        if member_filter and member_filter not in name:
            continue
        if require_file and not (path / require_file).is_file():
            continue
        batches.append(name)
    return batches


def validate_batch_selection(batch_id: str, member: str) -> None:
    if not BATCH_ID_PATTERN.fullmatch(batch_id):
        raise ValueError("잘못된 batch_id 형식입니다.")
    if not MEMBER_PATTERN.fullmatch(member):
        raise ValueError("잘못된 BATCH_MEMBER 형식입니다.")
    if member not in [part for part in batch_id.split("-") if part]:
        raise ValueError("선택한 배치는 현재 BATCH_MEMBER 소유가 아닙니다.")


def _load_json_object(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def summarize_submission(
    *,
    datasets_root: Path,
    outcome_root: Path,
    batch_id: str,
    member: str,
) -> dict:
    validate_batch_selection(batch_id, member)
    discovery_dir = datasets_root / "discovery" / batch_id
    outcome_dir = outcome_root / member / batch_id
    accepted_dir = datasets_root / "inbox" / "accepted" / batch_id
    report_path = outcome_dir / "validation_report.json"
    report = _load_json_object(report_path)
    manifest = _load_json_object(accepted_dir / "manifest.json")

    required_files = {
        "discovered_products.csv": (
            discovery_dir / "discovered_products.csv"
        ).is_file(),
        "crawled_products.csv": (discovery_dir / "crawled_products.csv").is_file(),
        "image_text_check.csv": (
            discovery_dir / "image_text_check.csv"
        ).is_file(),
        "products.csv": (outcome_dir / "products.csv").is_file(),
    }
    if manifest.get("status") == "ACCEPTED":
        status = "ACCEPTED"
    elif report.get("status") in {"READY", "REJECTED"}:
        status = str(report["status"])
    else:
        status = "READY" if all(required_files.values()) else "REJECTED"

    products = count_csv_rows(outcome_dir / "products.csv")
    failures = count_csv_rows(outcome_dir / "failures.csv")
    discovered = count_csv_rows(discovery_dir / "discovered_products.csv")
    crawled = count_csv_rows(discovery_dir / "crawled_products.csv")
    checks = count_csv_rows(discovery_dir / "image_text_check.csv")

    return {
        "kind": "submission",
        "batch_id": batch_id,
        "member": member,
        "status": status,
        "counts": {
            "discovered": discovered.row_count,
            "crawled": crawled.row_count,
            "image_checks": checks.row_count,
            "products": products.row_count,
            "failures": failures.row_count,
        },
        "required_files": required_files,
        "schema_versions": report.get("schema_versions", []),
        "parser_versions": report.get("parser_versions", []),
        "batch_sha256": report.get("batch_sha256"),
        "products_sha256": report.get("products_sha256"),
        "checksum_status": report.get("checksum_status", "NOT_VALIDATED"),
        "errors": report.get("errors", []),
        "report_exists": report_path.is_file(),
        "report_path": str(report_path),
        "accepted_manifest_path": str(accepted_dir / "manifest.json"),
    }
