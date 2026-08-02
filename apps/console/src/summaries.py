from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


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
