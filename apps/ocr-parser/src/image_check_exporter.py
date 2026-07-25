from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .text_presence import DetectMethod, TextPresence


IMAGE_CHECK_COLUMNS = [
    "schema_version",
    "batch_id",
    "original_product_id",
    "image_path",
    "text_presence",
    "detect_method",
    "confidence",
    "checked_at",
    "notes",
]


@dataclass(slots=True)
class ImageTextCheckRecord:
    batch_id: str
    original_product_id: str
    image_path: str
    text_presence: TextPresence | str
    detect_method: DetectMethod | str
    confidence: float | None
    checked_at: datetime
    notes: str = ""
    schema_version: str = "1.0"

    def to_row(self) -> dict[str, str]:
        presence = (
            self.text_presence.value
            if isinstance(self.text_presence, TextPresence)
            else str(self.text_presence)
        )
        method = (
            self.detect_method.value
            if isinstance(self.detect_method, DetectMethod)
            else str(self.detect_method)
        )
        return {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "original_product_id": self.original_product_id,
            "image_path": self.image_path,
            "text_presence": presence,
            "detect_method": method,
            "confidence": "" if self.confidence is None else str(self.confidence),
            "checked_at": self.checked_at.isoformat(),
            "notes": self.notes,
        }


def image_check_csv_path(discovery_root: Path, batch_id: str) -> Path:
    return discovery_root / batch_id / "image_text_check.csv"


def load_image_text_checks(path: Path) -> dict[str, str]:
    """image_path -> text_presence 매핑을 반환한다."""
    if not path.exists() or path.stat().st_size == 0:
        return {}
    mapping: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            image_path = (row.get("image_path") or "").strip()
            presence = (row.get("text_presence") or "").strip()
            if image_path and presence:
                mapping[image_path] = presence
    return mapping


def load_checked_image_paths(path: Path) -> set[str]:
    return set(load_image_text_checks(path))


def write_image_text_checks(records: list[ImageTextCheckRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=IMAGE_CHECK_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_row())
    return path


def merge_and_write_image_text_checks(
    existing_path: Path,
    new_records: list[ImageTextCheckRecord],
) -> Path:
    """기존 CSV와 신규 기록을 image_path 기준으로 병합해 저장한다."""
    by_path: dict[str, dict[str, str]] = {}
    if existing_path.exists() and existing_path.stat().st_size > 0:
        with existing_path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                image_path = (row.get("image_path") or "").strip()
                if image_path:
                    by_path[image_path] = {col: row.get(col, "") for col in IMAGE_CHECK_COLUMNS}

    for record in new_records:
        by_path[record.image_path] = record.to_row()

    existing_path.parent.mkdir(parents=True, exist_ok=True)
    with existing_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=IMAGE_CHECK_COLUMNS)
        writer.writeheader()
        for row in by_path.values():
            writer.writerow({col: row.get(col, "") for col in IMAGE_CHECK_COLUMNS})
    return existing_path
