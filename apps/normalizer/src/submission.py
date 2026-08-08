"""Local validation and atomic intake for collection batches."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from .adapters.products_csv import adapt_products_csv
from .checksum import with_content_hash
from .contracts import validate_payload

KST = ZoneInfo("Asia/Seoul")
BATCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
MEMBER_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,64}$")
REQUIRED_FILES = (
    "discovered_products.csv",
    "crawled_products.csv",
    "image_text_check.csv",
    "products.csv",
)


class SubmissionError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(slots=True)
class SubmissionReport:
    schema_version: str
    batch_id: str
    member: str
    status: str
    generated_at: str
    required_files: dict[str, bool]
    counts: dict[str, int]
    schema_versions: list[str]
    parser_versions: list[str]
    batch_sha256: str | None
    products_sha256: str | None
    submission_content_hash: str | None
    checksum_status: str
    errors: list[dict[str, str]] = field(default_factory=list)
    duplicate: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ValidationOutcome:
    report: SubmissionReport
    payload: dict[str, object] | None


def validate_batch_identity(batch_id: str, member: str) -> None:
    if not BATCH_ID_PATTERN.fullmatch(batch_id):
        raise SubmissionError(
            "INVALID_BATCH_ID",
            "batch_id는 영문·숫자로 시작하고 영문·숫자·_·-만 사용할 수 있습니다.",
        )
    if not MEMBER_PATTERN.fullmatch(member):
        raise SubmissionError(
            "INVALID_MEMBER",
            "member는 영문·숫자·_만 사용할 수 있습니다.",
        )
    if member not in [part for part in batch_id.split("-") if part]:
        raise SubmissionError(
            "BATCH_MEMBER_MISMATCH",
            f"batch_id '{batch_id}'는 member '{member}' 소유가 아닙니다.",
        )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def batch_sha256(files: dict[str, Path]) -> str | None:
    existing = {name: path for name, path in files.items() if path.is_file()}
    if not existing:
        return None
    digest = hashlib.sha256()
    for name in sorted(existing):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256(existing[name]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _count_csv_rows(path: Path) -> int:
    if not path.is_file() or path.stat().st_size == 0:
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return sum(1 for _ in csv.DictReader(file))


def _product_metadata(path: Path, batch_id: str) -> tuple[list[str], list[str]]:
    schema_versions: set[str] = set()
    parser_versions: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for index, row in enumerate(csv.DictReader(file), start=2):
            row_batch = (row.get("batch_id") or "").strip()
            if row_batch and row_batch != batch_id:
                raise SubmissionError(
                    "ROW_BATCH_ID_MISMATCH",
                    f"products.csv {index}행 batch_id '{row_batch}'가 선택 배치와 다릅니다.",
                )
            schema_version = (row.get("schema_version") or "").strip()
            parser_version = (row.get("parser_version") or "").strip()
            if schema_version:
                schema_versions.add(schema_version)
            if parser_version:
                parser_versions.add(parser_version)
    return sorted(schema_versions), sorted(parser_versions)


def _issue(error_code: str, path: str, message: str) -> dict[str, str]:
    return {"error_code": error_code, "path": path, "message": message}


def _accepted_artifact_uris(batch_id: str) -> dict[str, str | None]:
    base = f"/data/inbox/accepted/{batch_id}"
    return {
        "products_csv_uri": f"{base}/outcome/products.csv",
        "failures_csv_uri": f"{base}/outcome/failures.csv",
        "discovery_dir_uri": f"{base}/discovery",
    }


def validate_collection_batch(
    *,
    data_root: Path,
    outcome_root: Path,
    batch_id: str,
    member: str,
    contracts_dir: Path | None = None,
    manifest_status: str = "READY",
) -> ValidationOutcome:
    validate_batch_identity(batch_id, member)

    discovery_dir = data_root / "discovery" / batch_id
    outcome_dir = outcome_root / member / batch_id
    paths = {
        "discovered_products.csv": discovery_dir / "discovered_products.csv",
        "crawled_products.csv": discovery_dir / "crawled_products.csv",
        "image_text_check.csv": discovery_dir / "image_text_check.csv",
        "products.csv": outcome_dir / "products.csv",
    }
    required_files = {name: path.is_file() for name, path in paths.items()}
    errors = [
        _issue("REQUIRED_FILE_MISSING", f"$.required_files.{name}", str(paths[name]))
        for name in REQUIRED_FILES
        if not required_files[name]
    ]
    counts = {
        "discovered": _count_csv_rows(paths["discovered_products.csv"]),
        "crawled": _count_csv_rows(paths["crawled_products.csv"]),
        "image_checks": _count_csv_rows(paths["image_text_check.csv"]),
        "products": _count_csv_rows(paths["products.csv"]),
        "failures": _count_csv_rows(outcome_dir / "failures.csv"),
    }
    schema_versions: list[str] = []
    parser_versions: list[str] = []
    products_hash: str | None = None
    payload: dict[str, object] | None = None
    source_artifacts = {
        "discovery/discovered_products.csv": paths["discovered_products.csv"],
        "discovery/crawled_products.csv": paths["crawled_products.csv"],
        "discovery/image_text_check.csv": paths["image_text_check.csv"],
        "outcome/products.csv": paths["products.csv"],
        "outcome/failures.csv": outcome_dir / "failures.csv",
    }

    products_path = paths["products.csv"]
    if products_path.is_file():
        products_hash = file_sha256(products_path)
        try:
            schema_versions, parser_versions = _product_metadata(
                products_path, batch_id
            )
            payload = adapt_products_csv(
                products_path,
                batch_id=batch_id,
                member=member,
                status=manifest_status,
                failures_csv=(
                    outcome_dir / "failures.csv"
                    if (outcome_dir / "failures.csv").is_file()
                    else None
                ),
                discovery_dir=discovery_dir,
            )
            payload["artifacts"] = _accepted_artifact_uris(batch_id)
            payload = with_content_hash(payload)
            result = validate_payload(
                "collection_submission",
                payload,
                contracts_dir=contracts_dir,
                check_checksum=True,
            )
            errors.extend(
                _issue(issue.error_code, issue.path, issue.message)
                for issue in result.issues
            )
        except SubmissionError as error:
            errors.append(_issue(error.error_code, "$.products", str(error)))
        except (ValueError, TypeError, csv.Error, ValidationError) as error:
            errors.append(
                _issue("PRODUCTS_ADAPTER_FAILED", "$.products", str(error))
            )

    generated_at = datetime.now(KST).isoformat()
    report = SubmissionReport(
        schema_version="1.0.0",
        batch_id=batch_id,
        member=member,
        status="REJECTED" if errors else "READY",
        generated_at=generated_at,
        required_files=required_files,
        counts=counts,
        schema_versions=schema_versions,
        parser_versions=parser_versions,
        batch_sha256=batch_sha256(source_artifacts),
        products_sha256=products_hash,
        submission_content_hash=(
            str(payload["content_hash"]) if payload is not None else None
        ),
        checksum_status=(
            "VALID" if payload is not None and not errors else "INVALID"
        ),
        errors=errors,
    )
    return ValidationOutcome(report=report, payload=payload)


def write_validation_report(report: SubmissionReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def local_report_path(outcome_root: Path, member: str, batch_id: str) -> Path:
    validate_batch_identity(batch_id, member)
    return outcome_root / member / batch_id / "validation_report.json"


def validate_and_write_report(
    *,
    data_root: Path,
    outcome_root: Path,
    batch_id: str,
    member: str,
    contracts_dir: Path | None = None,
) -> SubmissionReport:
    outcome = validate_collection_batch(
        data_root=data_root,
        outcome_root=outcome_root,
        batch_id=batch_id,
        member=member,
        contracts_dir=contracts_dir,
    )
    write_validation_report(
        outcome.report, local_report_path(outcome_root, member, batch_id)
    )
    return outcome.report


def _validate_existing_manifest(
    path: Path, contracts_dir: Path | None
) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SubmissionError(
            "ACCEPTED_MANIFEST_INVALID", f"기존 manifest를 읽을 수 없습니다: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise SubmissionError(
            "ACCEPTED_MANIFEST_INVALID", "기존 manifest root가 object가 아닙니다."
        )
    result = validate_payload(
        "collection_submission",
        payload,
        contracts_dir=contracts_dir,
        check_checksum=True,
    )
    if not result.ok:
        message = "; ".join(f"{item.path}: {item.message}" for item in result.issues)
        raise SubmissionError("ACCEPTED_MANIFEST_INVALID", message)
    return payload


def submit_collection_batch(
    *,
    data_root: Path,
    outcome_root: Path,
    batch_id: str,
    member: str,
    contracts_dir: Path | None = None,
) -> SubmissionReport:
    outcome = validate_collection_batch(
        data_root=data_root,
        outcome_root=outcome_root,
        batch_id=batch_id,
        member=member,
        contracts_dir=contracts_dir,
        manifest_status="ACCEPTED",
    )
    report = outcome.report
    if report.errors or outcome.payload is None:
        write_validation_report(
            report, local_report_path(outcome_root, member, batch_id)
        )
        raise SubmissionError(
            "COLLECTION_VALIDATION_FAILED",
            "배치 검증에 실패했습니다. validation_report.json을 확인하세요.",
        )

    accepted_root = data_root / "inbox" / "accepted"
    accepted_root.mkdir(parents=True, exist_ok=True)
    final_dir = accepted_root / batch_id
    source_products = outcome_root / member / batch_id / "products.csv"

    if final_dir.exists():
        accepted_products = final_dir / "outcome" / "products.csv"
        manifest_path = final_dir / "manifest.json"
        accepted_artifacts = {
            "discovery/discovered_products.csv": (
                final_dir / "discovery" / "discovered_products.csv"
            ),
            "discovery/crawled_products.csv": (
                final_dir / "discovery" / "crawled_products.csv"
            ),
            "discovery/image_text_check.csv": (
                final_dir / "discovery" / "image_text_check.csv"
            ),
            "outcome/products.csv": accepted_products,
            "outcome/failures.csv": final_dir / "outcome" / "failures.csv",
        }
        if (
            accepted_products.is_file()
            and batch_sha256(accepted_artifacts) == report.batch_sha256
            and manifest_path.is_file()
        ):
            existing = _validate_existing_manifest(manifest_path, contracts_dir)
            if existing.get("status") != "ACCEPTED":
                raise SubmissionError(
                    "ACCEPTED_MANIFEST_INVALID",
                    "기존 manifest 상태가 ACCEPTED가 아닙니다.",
                )
            report.status = "ACCEPTED"
            report.duplicate = True
            report.submission_content_hash = str(existing["content_hash"])
            write_validation_report(
                report, local_report_path(outcome_root, member, batch_id)
            )
            return report
        raise SubmissionError(
            "BATCH_ALREADY_ACCEPTED_DIFFERENT_CONTENT",
            f"다른 내용의 accepted batch가 이미 존재합니다: {final_dir}",
        )

    temporary_dir = accepted_root / f".{batch_id}.{uuid.uuid4().hex}.tmp"
    try:
        discovery_source = data_root / "discovery" / batch_id
        outcome_source = outcome_root / member / batch_id
        shutil.copytree(discovery_source, temporary_dir / "discovery")
        (temporary_dir / "outcome").mkdir(parents=True)
        shutil.copy2(source_products, temporary_dir / "outcome" / "products.csv")
        failures = outcome_source / "failures.csv"
        if failures.is_file():
            shutil.copy2(failures, temporary_dir / "outcome" / "failures.csv")

        copied_artifacts = {
            "discovery/discovered_products.csv": (
                temporary_dir / "discovery" / "discovered_products.csv"
            ),
            "discovery/crawled_products.csv": (
                temporary_dir / "discovery" / "crawled_products.csv"
            ),
            "discovery/image_text_check.csv": (
                temporary_dir / "discovery" / "image_text_check.csv"
            ),
            "outcome/products.csv": temporary_dir / "outcome" / "products.csv",
            "outcome/failures.csv": temporary_dir / "outcome" / "failures.csv",
        }
        if batch_sha256(copied_artifacts) != report.batch_sha256:
            raise SubmissionError(
                "COPY_CHECKSUM_MISMATCH",
                "임시 제출 디렉터리의 산출물 checksum이 원본과 다릅니다.",
            )

        manifest_path = temporary_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(outcome.payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _validate_existing_manifest(manifest_path, contracts_dir)

        report.status = "ACCEPTED"
        report.checksum_status = "VALID"
        write_validation_report(report, temporary_dir / "validation_report.json")
        os.replace(temporary_dir, final_dir)
    except Exception:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)
        raise

    write_validation_report(
        report, local_report_path(outcome_root, member, batch_id)
    )
    return report
