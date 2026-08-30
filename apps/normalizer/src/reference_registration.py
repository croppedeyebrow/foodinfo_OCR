from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import validate_payload
from .kfia_export_columns import (
    DATASET_VERSION_PATTERN,
    EXPORT_FILENAME,
    missing_required_native_columns,
    read_native_export,
    summarize_native_export,
)
from .kurly_transform.common import atomic_write_json, now_iso
from .storage_paths import reference_inbox_dir
from .submission import file_sha256


class DatasetVersionConflictError(ValueError):
    """Raised when the same dataset version already exists with a different checksum."""


@dataclass(slots=True)
class ReferenceRegistrationResult:
    dataset_version: str
    manifest_path: Path
    export_path: Path
    row_count: int
    duplicate: bool
    manifest: dict[str, Any]


def validate_dataset_version(dataset_version: str) -> None:
    if not DATASET_VERSION_PATTERN.match(dataset_version.strip()):
        raise ValueError(
            "dataset version은 영문·숫자로 시작하고 128자 이하여야 합니다. "
            "예: KFIA-2026-08"
        )


def list_reference_datasets(data_root: Path) -> list[str]:
    inbox_root = data_root / "reference" / "inbox"
    if not inbox_root.is_dir():
        return []
    versions: list[str] = []
    for child in sorted(inbox_root.iterdir()):
        if child.is_dir() and (child / "manifest.json").is_file():
            versions.append(child.name)
    return versions


def _manifest_path(data_root: Path, dataset_version: str) -> Path:
    return reference_inbox_dir(data_root, dataset_version) / "manifest.json"


def load_reference_manifest(data_root: Path, dataset_version: str) -> dict[str, Any] | None:
    path = _manifest_path(data_root, dataset_version)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def validate_reference_export(export_path: Path) -> dict[str, Any]:
    if not export_path.is_file():
        raise FileNotFoundError(f"export file not found: {export_path}")
    frame = read_native_export(export_path)
    missing = missing_required_native_columns(frame)
    if missing:
        raise ValueError(
            "필수 컬럼이 없습니다: " + ", ".join(missing)
        )
    row_count = frame.height
    if row_count <= 0:
        raise ValueError("export CSV에 데이터 행이 없습니다.")
    summary = summarize_native_export(frame)
    summary["export_checksum"] = file_sha256(export_path)
    contract = validate_payload("kfia_native_export", summary)
    if not contract.ok:
        raise ValueError(contract.issues[0].message)
    return summary


def default_reference_parser_version() -> str:
    return os.getenv("PIPELINE_CODE_VERSION", "").strip() or "unknown"


def register_reference_export(
    *,
    data_root: Path,
    dataset_version: str,
    export_path: Path,
    registered_by: str,
    parser_version: str | None = None,
) -> ReferenceRegistrationResult:
    validate_dataset_version(dataset_version)
    resolved_parser_version = (parser_version or "").strip() or default_reference_parser_version()
    registered_by = registered_by.strip()
    if not registered_by:
        raise ValueError("등록자는 필수입니다.")

    validation = validate_reference_export(export_path)
    export_checksum = str(validation["export_checksum"])
    row_count = int(validation["row_count"])

    inbox_dir = reference_inbox_dir(data_root, dataset_version)
    manifest_path = inbox_dir / "manifest.json"
    export_target = inbox_dir / EXPORT_FILENAME

    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        existing_checksum = str(existing.get("export_checksum") or "")
        if existing_checksum == export_checksum:
            return ReferenceRegistrationResult(
                dataset_version=dataset_version,
                manifest_path=manifest_path,
                export_path=export_target,
                row_count=int(existing.get("row_count") or row_count),
                duplicate=True,
                manifest=existing,
            )
        raise DatasetVersionConflictError(
            f"dataset version {dataset_version} already exists with a different export checksum"
        )

    inbox_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(export_path, export_target)

    manifest_payload = {
        "schema_version": "1.0.0",
        "dataset_version": dataset_version,
        "source": "KFIA_REFERENCE",
        "parser_version": resolved_parser_version,
        "registered_by": registered_by,
        "registered_at": now_iso(),
        "status": "REGISTERED",
        "export_filename": EXPORT_FILENAME,
        "export_checksum": export_checksum,
        "row_count": row_count,
        "validation_status": None,
        "duplicate": False,
    }
    contract = validate_payload("kfia_reference_manifest", manifest_payload)
    if not contract.ok:
        raise ValueError(contract.issues[0].message)

    atomic_write_json(manifest_path, manifest_payload)
    return ReferenceRegistrationResult(
        dataset_version=dataset_version,
        manifest_path=manifest_path,
        export_path=export_target,
        row_count=row_count,
        duplicate=False,
        manifest=manifest_payload,
    )


def mark_reference_validated(data_root: Path, dataset_version: str) -> dict[str, Any]:
    manifest_path = _manifest_path(data_root, dataset_version)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"reference manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "VALIDATED"
    manifest["validation_status"] = "OK"
    atomic_write_json(manifest_path, manifest)
    return manifest
