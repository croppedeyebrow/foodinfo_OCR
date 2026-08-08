"""Adapter from an accepted collection bundle to pipeline metadata rows."""

from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ..contracts import load_json_file, validate_payload
from ..submission import file_sha256, validate_batch_identity
from .models import (
    ArtifactLineageCreate,
    PipelineArtifactCreate,
    PipelineRunCreate,
    PipelineStepCreate,
    RunStatus,
    TriggerType,
)
from .repository import MetadataRepository

INTAKE_STEP_KEY = "collection_submission_intake"


def _csv_metadata(path: Path) -> tuple[int, str | None]:
    if not path.is_file() or path.stat().st_size == 0:
        return 0, None
    versions: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    for row in rows:
        version = (row.get("schema_version") or "").strip()
        if version:
            versions.add(version)
    return len(rows), ",".join(sorted(versions)) or None


def _artifact_id(
    run_id: str, logical_name: str, checksum: str
) -> str:
    value = f"{run_id}:{logical_name}:{checksum}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, value))


def _artifact_record(
    *,
    run_id: str,
    logical_name: str,
    path: Path,
    code_version: str,
) -> PipelineArtifactCreate:
    checksum = file_sha256(path)
    suffix = path.suffix.lower().lstrip(".") or "binary"
    row_count: int | None = None
    schema_version: str | None = None
    if suffix == "csv":
        row_count, schema_version = _csv_metadata(path)
    elif path.name == "manifest.json":
        payload = load_json_file(path)
        schema_version = str(payload.get("schema_version") or "") or None
        row_count = int(payload.get("row_count") or 0)
    return PipelineArtifactCreate(
        artifact_id=_artifact_id(run_id, logical_name, checksum),
        run_id=run_id,
        step_key=INTAKE_STEP_KEY,
        step_attempt=1,
        logical_name=logical_name,
        path=path.as_posix(),
        format=suffix.upper(),
        schema_version=schema_version,
        checksum=checksum,
        row_count=row_count,
        byte_size=path.stat().st_size,
        code_version=code_version,
    )


def _accepted_files(batch_dir: Path) -> dict[str, Path]:
    candidates = {
        "discovered_products": (
            batch_dir / "discovery" / "discovered_products.csv"
        ),
        "crawled_products": batch_dir / "discovery" / "crawled_products.csv",
        "image_text_check": (
            batch_dir / "discovery" / "image_text_check.csv"
        ),
        "products": batch_dir / "outcome" / "products.csv",
        "failures": batch_dir / "outcome" / "failures.csv",
        "collection_manifest": batch_dir / "manifest.json",
        "validation_report": batch_dir / "validation_report.json",
    }
    return {name: path for name, path in candidates.items() if path.is_file()}


def register_accepted_submission(
    repository: MetadataRepository,
    *,
    data_root: Path,
    batch_id: str,
    member: str,
    code_version: str,
    contracts_dir: Path | None = None,
) -> dict[str, Any]:
    validate_batch_identity(batch_id, member)
    batch_dir = data_root / "inbox" / "accepted" / batch_id
    manifest_path = batch_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"accepted manifest not found: {manifest_path}")

    manifest = load_json_file(manifest_path)
    result = validate_payload(
        "collection_submission",
        manifest,
        contracts_dir=contracts_dir,
        check_checksum=True,
    )
    if not result.ok:
        issues = "; ".join(
            f"{issue.error_code}:{issue.path}:{issue.message}"
            for issue in result.issues
        )
        raise ValueError(f"invalid accepted manifest: {issues}")
    if manifest.get("status") != "ACCEPTED":
        raise ValueError("accepted manifest status must be ACCEPTED")
    if manifest.get("batch_id") != batch_id or manifest.get("member") != member:
        raise ValueError("accepted manifest batch/member mismatch")

    config_hash = str(manifest["content_hash"])
    run_id = f"collection-intake:{batch_id}:{config_hash[:16]}"
    created_at = datetime.fromisoformat(str(manifest["created_at"]))
    run = repository.create_run(
        PipelineRunCreate(
            run_id=run_id,
            pipeline_name="collection_intake",
            batch_id=batch_id,
            trigger_type=TriggerType.EXTERNAL_SUBMISSION,
            status=RunStatus.PENDING,
            code_version=code_version,
            config_hash=config_hash,
        )
    )
    if run["status"] == RunStatus.SUCCEEDED.value:
        snapshot = repository.get_run(run_id)
        assert snapshot is not None
        return snapshot

    if run["status"] == RunStatus.PENDING.value:
        repository.transition_run(run_id, RunStatus.RUNNING, at=created_at)

    files = _accepted_files(batch_dir)
    repository.create_step(
        PipelineStepCreate(
            run_id=run_id,
            step_key=INTAKE_STEP_KEY,
            attempt=1,
            status=RunStatus.PENDING,
            input_count=len(files),
        )
    )
    snapshot = repository.get_run(run_id)
    assert snapshot is not None
    step = next(
        item
        for item in snapshot["steps"]
        if item["step_key"] == INTAKE_STEP_KEY and item["attempt"] == 1
    )
    if step["status"] == RunStatus.PENDING.value:
        repository.transition_step(
            run_id, INTAKE_STEP_KEY, 1, RunStatus.RUNNING, at=created_at
        )

    registered: dict[str, dict[str, Any]] = {}
    for logical_name, path in files.items():
        registered[logical_name] = repository.register_artifact(
            _artifact_record(
                run_id=run_id,
                logical_name=logical_name,
                path=path,
                code_version=code_version,
            )
        )

    manifest_artifact = registered["collection_manifest"]
    for logical_name, artifact in registered.items():
        if logical_name == "collection_manifest":
            continue
        repository.add_lineage(
            ArtifactLineageCreate(
                parent_artifact_id=artifact["artifact_id"],
                child_artifact_id=manifest_artifact["artifact_id"],
                relation_type="BUNDLED_IN",
            )
        )

    repository.transition_step(
        run_id,
        INTAKE_STEP_KEY,
        1,
        RunStatus.SUCCEEDED,
        output_count=len(registered),
        failed_count=0,
    )
    repository.transition_run(run_id, RunStatus.SUCCEEDED)
    snapshot = repository.get_run(run_id)
    assert snapshot is not None
    return snapshot
