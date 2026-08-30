"""Contract registry, JSON Schema validation, and version gates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .checksum import compute_content_hash, with_content_hash

SUPPORTED_MAJOR = {
    "collection_submission": {1},
    "kurly_raw_product": {1},
    "kfia_native_export": {1},
    "kfia_reference_manifest": {1},
    "kfia_reference_bronze": {1},
    "kfia_reference_silver": {1},
    "mfds_raw_record": {1},
    "normalized_freshness": {1},
    "reconciled_freshness": {1},
    "review_decision": {1},
    "gold_freshness": {1},
    "ocr_record": {1},
}

CONTRACT_SCHEMA_FILES = {
    "collection_submission": "collection_submission.schema.json",
    "kurly_raw_product": "kurly_raw_product.schema.json",
    "kfia_reference_manifest": "kfia_reference_manifest.schema.json",
    "kfia_native_export": "kfia_native_export.schema.json",
    "kfia_reference_bronze": "kfia_reference_bronze.schema.json",
    "kfia_reference_silver": "kfia_reference_silver.schema.json",
    "mfds_raw_record": "mfds_raw_record.schema.json",
    "normalized_freshness": "normalized_freshness.schema.json",
    "reconciled_freshness": "reconciled_freshness.schema.json",
    "review_decision": "review_decision.schema.json",
    "gold_freshness": "gold_freshness.schema.json",
    "ocr_record": "ocr_record.schema.json",
}


class ContractMeta(BaseModel):
    """Shared metadata required by every platform contract (v1)."""

    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0.0"
    run_id: str
    batch_id: str
    record_id: str
    source: str
    source_record_id: str
    source_uri: str | None = None
    content_hash: str
    parser_version: str
    created_at: str


class SubmittedProduct(ContractMeta):
    original_product_id: str
    product_name_raw: str
    product_url: str
    food_name_candidate: str | None = None
    sales_unit_raw: str | None = None
    weight_raw: str | None = None
    quantity_raw: str | None = None
    food_type_raw: str | None = None
    food_type_source: str | None = None
    expiration_info_raw: str | None = None
    expiration_source: str | None = None
    storage_method_raw: str | None = None
    storage_source: str | None = None
    storage_type: str | None = None
    ocr_confidence: float | None = None
    crawl_collected_at: str | None = None
    ocr_collected_at: str | None = None
    validation_status: str | None = None
    parse_status: str | None = None
    image_sha256: str | None = None


class CollectionSubmissionArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    products_csv_uri: str
    failures_csv_uri: str | None = None
    discovery_dir_uri: str | None = None


class CollectionSubmission(ContractMeta):
    source: str = "KURLY_COLLECTION"
    member: str
    status: str = "DRAFT"
    row_count: int = Field(ge=0)
    supported_consumer_versions: list[str] = Field(default_factory=lambda: ["1.0.0"])
    artifacts: CollectionSubmissionArtifacts
    products: list[SubmittedProduct]


class KurlyRawProduct(ContractMeta):
    source: str = "KURLY"
    original_product_id: str
    product_url: str
    product_name_raw: str | None = None
    requested_url: str | None = None
    food_name_candidate: str | None = None
    sales_unit_raw: str | None = None
    weight_raw: str | None = None
    quantity_raw: str | None = None
    expiration_info_dom: str | None = None
    storage_method_dom: str | None = None
    storage_type_dom: str | None = None
    detail_image_urls: list[str] = Field(default_factory=list)
    local_image_paths: list[str] = Field(default_factory=list)
    crawl_status: str | None = None
    collected_at: str | None = None


class MfdsRawRecord(ContractMeta):
    source: str = "MFDS"
    document_id: str
    raw_text: str
    page_number: int | None = None
    food_name_raw: str | None = None
    storage_method_raw: str | None = None
    expiration_info_raw: str | None = None


class NormalizedFreshness(ContractMeta):
    food_name_normalized: str
    storage_type: str
    expiration_value: float | None = None
    expiration_unit: str | None = None
    expiration_basis: str | None = None
    expiration_text_raw: str | None = None


class ReconciledFreshness(ContractMeta):
    source: str = "RECONCILER"
    kurly_record_id: str
    review_status: str
    match_type: str
    confidence: float
    rule_id: str
    rule_version: str
    selected_source: str
    mfds_record_id: str | None = None
    kurly_expiration_text: str | None = None
    mfds_expiration_text: str | None = None
    selected_expiration_text: str | None = None
    selected_storage_type: str | None = None


class GoldFreshness(ContractMeta):
    source: str = "GOLD"
    dataset_version: str
    external_product_id: str
    food_mapping_key: str
    product_name: str
    storage_type: str
    selected_source: str
    confidence: float
    review_status: str
    expiration_value: float | None = None
    expiration_unit: str | None = None
    expiration_basis: str | None = None


PYDANTIC_MODELS: dict[str, type[BaseModel]] = {
    "collection_submission": CollectionSubmission,
    "kurly_raw_product": KurlyRawProduct,
    "mfds_raw_record": MfdsRawRecord,
    "normalized_freshness": NormalizedFreshness,
    "reconciled_freshness": ReconciledFreshness,
    "gold_freshness": GoldFreshness,
}


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    error_code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    ok: bool
    contract: str
    issues: list[ValidationIssue]

    @property
    def error_codes(self) -> list[str]:
        return [issue.error_code for issue in self.issues]


def default_contracts_dir() -> Path:
    env_override = Path("/app/contracts")
    if env_override.is_dir():
        return env_override
    return Path(__file__).resolve().parents[3] / "contracts"


def parse_schema_version(version: str) -> tuple[int, int, int]:
    parts = version.strip().split(".")
    if len(parts) < 1:
        raise ValueError(f"empty schema_version: {version!r}")
    major = int(parts[0])
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0
    return major, minor, patch


def load_schema(contract: str, contracts_dir: Path | None = None) -> dict[str, Any]:
    if contract not in CONTRACT_SCHEMA_FILES:
        raise KeyError(f"unknown contract: {contract}")
    root = contracts_dir or default_contracts_dir()
    path = root / CONTRACT_SCHEMA_FILES[contract]
    return json.loads(path.read_text(encoding="utf-8"))


def _json_path(error: jsonschema.ValidationError) -> str:
    if not error.path:
        return "$"
    parts: list[str] = ["$"]
    for item in error.path:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            parts.append(f".{item}")
    return "".join(parts)


def check_major_version(contract: str, payload: dict[str, Any]) -> ValidationIssue | None:
    version = payload.get("schema_version")
    if not isinstance(version, str) or not version.strip():
        return ValidationIssue(
            error_code="MISSING_SCHEMA_VERSION",
            path="$.schema_version",
            message="schema_version is required",
        )
    try:
        major, _, _ = parse_schema_version(version)
    except ValueError:
        return ValidationIssue(
            error_code="INVALID_SCHEMA_VERSION",
            path="$.schema_version",
            message=f"unparseable schema_version: {version!r}",
        )
    allowed = SUPPORTED_MAJOR.get(contract, set())
    if major not in allowed:
        return ValidationIssue(
            error_code="UNSUPPORTED_SCHEMA_VERSION",
            path="$.schema_version",
            message=(
                f"major version {major} is not supported for {contract}; "
                f"supported majors={sorted(allowed)}"
            ),
        )
    return None


def validate_payload(
    contract: str,
    payload: dict[str, Any],
    *,
    contracts_dir: Path | None = None,
    check_checksum: bool = True,
) -> ValidationResult:
    issues: list[ValidationIssue] = []

    version_issue = check_major_version(contract, payload)
    if version_issue is not None:
        issues.append(version_issue)
        if version_issue.error_code == "UNSUPPORTED_SCHEMA_VERSION":
            return ValidationResult(ok=False, contract=contract, issues=issues)

    try:
        schema = load_schema(contract, contracts_dir)
    except FileNotFoundError as error:
        return ValidationResult(
            ok=False,
            contract=contract,
            issues=[
                ValidationIssue(
                    error_code="SCHEMA_NOT_FOUND",
                    path="$",
                    message=str(error),
                )
            ],
        )

    validator = Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
        issues.append(
            ValidationIssue(
                error_code="SCHEMA_VALIDATION_FAILED",
                path=_json_path(error),
                message=error.message,
            )
        )

    model_cls = PYDANTIC_MODELS.get(contract)
    if model_cls is not None and not any(
        issue.error_code == "SCHEMA_VALIDATION_FAILED" for issue in issues
    ):
        try:
            model_cls.model_validate(payload)
        except ValidationError as error:
            for item in error.errors():
                loc = ".".join(str(part) for part in item.get("loc", ()))
                issues.append(
                    ValidationIssue(
                        error_code="PYDANTIC_VALIDATION_FAILED",
                        path=f"$.{loc}" if loc else "$",
                        message=item.get("msg", "validation error"),
                    )
                )

    if check_checksum and "content_hash" in payload:
        expected = payload.get("content_hash")
        actual = compute_content_hash(payload)
        if expected != actual:
            issues.append(
                ValidationIssue(
                    error_code="CHECKSUM_MISMATCH",
                    path="$.content_hash",
                    message=f"expected {actual}, got {expected}",
                )
            )

    return ValidationResult(ok=not issues, contract=contract, issues=issues)


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"INVALID_JSON: {path}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"INVALID_JSON: root must be an object: {path}")
    return data


def seal_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Fill content_hash using canonical rules."""
    return with_content_hash(payload)
