from __future__ import annotations

import csv
import json
import re
from collections import Counter
from collections.abc import Sequence
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


def infer_batch_member(batch_id: str, team_members: Sequence[str]) -> str | None:
    parts = [part for part in batch_id.split("-") if part]
    for member in team_members:
        if member in parts:
            return member
    return None


def format_discovery_source(manifest: dict) -> dict[str, str]:
    mode = str(manifest.get("source_mode") or "").strip().upper()
    value = str(manifest.get("source_value") or "").strip()
    labels = {
        "SEARCH": "검색",
        "CATEGORY": "카테고리",
        "URL_LIST": "URL목록",
    }
    mode_label = labels.get(mode, mode or "미확인")
    if value:
        display = f"{mode_label}: {value}"
    else:
        display = mode_label
    return {
        "source_mode": mode or "UNKNOWN",
        "source_value": value,
        "source_label": display,
    }


def summarize_team_batches(
    *,
    datasets_root: Path,
    outcome_root: Path,
    team_members: Sequence[str],
) -> list[dict]:
    discovery_root = datasets_root / "discovery"
    accepted_root = datasets_root / "inbox" / "accepted"
    rows: list[dict] = []
    for batch_id in list_discovery_batches(
        discovery_root,
        require_file="crawled_products.csv",
    ):
        member = infer_batch_member(batch_id, team_members)
        if member is None:
            continue
        discovery_dir = discovery_root / batch_id
        outcome_dir = outcome_root / member / batch_id
        discovered = count_csv_rows(discovery_dir / "discovered_products.csv")
        crawled = count_csv_rows(discovery_dir / "crawled_products.csv")
        checks = count_csv_rows(discovery_dir / "image_text_check.csv")
        products = count_csv_rows(outcome_dir / "products.csv")
        accepted = (accepted_root / batch_id / "manifest.json").is_file()
        source = format_discovery_source(
            _load_json_object(discovery_dir / "manifest.json")
        )
        if accepted:
            pipeline_status = "ACCEPTED"
        elif products.exists and products.row_count > 0:
            pipeline_status = "OCR_DONE"
        elif crawled.exists and crawled.row_count > 0:
            pipeline_status = "CRAWLED"
        else:
            pipeline_status = "IN_PROGRESS"
        rows.append(
            {
                "batch_id": batch_id,
                "member": member,
                "discovered": discovered.row_count,
                "crawled": crawled.row_count,
                "image_checks": checks.row_count,
                "products": products.row_count,
                "pipeline_status": pipeline_status,
                "accepted": accepted,
                **source,
            }
        )
    return rows


def validate_batch_selection(batch_id: str, member: str) -> None:
    if not BATCH_ID_PATTERN.fullmatch(batch_id):
        raise ValueError("잘못된 batch_id 형식입니다.")
    if not MEMBER_PATTERN.fullmatch(member):
        raise ValueError("잘못된 BATCH_MEMBER 형식입니다.")
    if member not in [part for part in batch_id.split("-") if part]:
        raise ValueError("선택한 배치는 현재 BATCH_MEMBER 소유가 아닙니다.")


def validate_operator_batch_selection(
    batch_id: str,
    member: str,
    allowed_members: Sequence[str],
) -> None:
    if not BATCH_ID_PATTERN.fullmatch(batch_id):
        raise ValueError("잘못된 batch_id 형식입니다.")
    if not MEMBER_PATTERN.fullmatch(member):
        raise ValueError("잘못된 member 형식입니다.")
    if member not in allowed_members:
        raise ValueError(f"운영자가 처리할 수 없는 생산자입니다: {member}")
    if member not in [part for part in batch_id.split("-") if part]:
        raise ValueError(f"batch_id '{batch_id}'는 member '{member}' 소유가 아닙니다.")


OPERATOR_STATUS_LABELS = {
    "UNVALIDATED": "미검증",
    "VALIDATED": "검증성공",
    "SUBMITTED": "제출완료",
    "FAILED": "실패",
}


def operator_submission_status(
    *,
    accepted: bool,
    report_status: str | None,
    required_files_ok: bool,
) -> tuple[str, str]:
    if accepted:
        return "SUBMITTED", OPERATOR_STATUS_LABELS["SUBMITTED"]
    if report_status == "READY":
        return "VALIDATED", OPERATOR_STATUS_LABELS["VALIDATED"]
    if report_status == "REJECTED" or not required_files_ok:
        return "FAILED", OPERATOR_STATUS_LABELS["FAILED"]
    return "UNVALIDATED", OPERATOR_STATUS_LABELS["UNVALIDATED"]


def summarize_operator_batches(
    *,
    datasets_root: Path,
    outcome_root: Path,
    allowed_members: Sequence[str],
    member_filter: str | None = None,
    include_submitted: bool = True,
) -> list[dict]:
    rows: list[dict] = []
    for row in summarize_team_batches(
        datasets_root=datasets_root,
        outcome_root=outcome_root,
        team_members=allowed_members,
    ):
        if row["products"] <= 0:
            continue
        if member_filter and row["member"] != member_filter:
            continue
        if not include_submitted and row["accepted"]:
            continue
        try:
            submission = summarize_submission(
                datasets_root=datasets_root,
                outcome_root=outcome_root,
                batch_id=row["batch_id"],
                member=row["member"],
            )
        except ValueError:
            continue
        status_code, status_label = operator_submission_status(
            accepted=row["accepted"],
            report_status=str(submission.get("status") or ""),
            required_files_ok=all(submission.get("required_files", {}).values()),
        )
        rows.append(
            {
                **row,
                "submission_status": status_code,
                "submission_status_label": status_label,
                "validation_report_exists": submission.get("report_exists", False),
            }
        )
    return rows


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
