from __future__ import annotations

import json
import uuid
from pathlib import Path

from ...metadata.models import PipelineArtifactCreate
from ...reconciliation import parse_reconcile_pair_id, run_kurly_kfia_reconcile
from ...storage_paths import reconciled_pair_dir, silver_batch_dir
from ...submission import file_sha256
from .base import StageContext, StageExecutionResult, StageService


class KurlyKfiaReconcileStage:
    stage_key = "kurly_kfia_reconcile"
    display_name = "Kurly–KFIA 대조"
    prerequisites = ("kurly_silver", "kfia_reference_silver")

    def check_prerequisites(self, context: StageContext) -> list[str]:
        try:
            kurly_batch_id, kfia_dataset_version = parse_reconcile_pair_id(context.batch_id)
        except ValueError as error:
            return [str(error)]

        kurly_manifest = (
            silver_batch_dir(context.data_root, "kurly", kurly_batch_id) / "manifest.json"
        )
        if not kurly_manifest.is_file():
            return [
                "Kurly Silver manifest가 없습니다. Kurly Silver를 먼저 실행하세요."
            ]
        kfia_manifest = (
            silver_batch_dir(context.data_root, "kfia", kfia_dataset_version)
            / "manifest.json"
        )
        if not kfia_manifest.is_file():
            return [
                "KFIA Reference Silver manifest가 없습니다. Reference Silver를 먼저 실행하세요."
            ]
        try:
            kurly_payload = json.loads(kurly_manifest.read_text(encoding="utf-8"))
            kfia_payload = json.loads(kfia_manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ["Silver manifest JSON이 손상되었습니다."]
        if int(kurly_payload.get("unique_product_count") or 0) <= 0:
            return ["Kurly Silver에 유효 레코드가 없습니다."]
        if int(kfia_payload.get("record_count") or 0) <= 0:
            return ["KFIA Reference Silver에 유효 레코드가 없습니다."]
        return []

    def execute(self, context: StageContext) -> StageExecutionResult:
        errors = self.check_prerequisites(context)
        if errors:
            return StageExecutionResult(
                failed_count=1,
                error_code="PREREQUISITE_NOT_MET",
                error_message=errors[0],
            )
        try:
            result = run_kurly_kfia_reconcile(
                data_root=context.data_root,
                pair_id=context.batch_id,
                run_id=context.run_id or f"batch:{context.batch_id}:{self.stage_key}",
                code_version=context.code_version,
                attempt=context.attempt,
            )
        except Exception as error:
            return StageExecutionResult(
                failed_count=1,
                error_code="RECONCILE_STAGE_FAILED",
                error_message=str(error),
            )

        checksum = file_sha256(result.manifest_path)
        return StageExecutionResult(
            input_count=result.input_count,
            output_count=result.record_count,
            failed_count=0,
            progress_message=(
                f"대조 입력 {result.input_count}건 · 승인 {result.approved_count}건 · "
                f"검토 {result.review_required_count}건 · 미기준 {result.no_reference_count}건"
            ),
            artifacts=[
                PipelineArtifactCreate(
                    artifact_id=str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"{context.batch_id}:{self.stage_key}:{checksum}",
                        )
                    ),
                    run_id="pending",
                    step_key=self.stage_key,
                    step_attempt=context.attempt,
                    logical_name="reconciled_manifest",
                    path=result.manifest_path.as_posix(),
                    format="JSON",
                    schema_version="1.0.0",
                    checksum=checksum,
                    row_count=result.record_count,
                    byte_size=result.manifest_path.stat().st_size,
                    code_version=context.code_version,
                ),
                PipelineArtifactCreate(
                    artifact_id=str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"{context.batch_id}:{self.stage_key}:records:{checksum}",
                        )
                    ),
                    run_id="pending",
                    step_key=self.stage_key,
                    step_attempt=context.attempt,
                    logical_name="reconciled_records",
                    path=result.records_path.as_posix(),
                    format="PARQUET",
                    schema_version="1.0.0",
                    checksum=file_sha256(result.records_path),
                    row_count=result.record_count,
                    byte_size=result.records_path.stat().st_size,
                    code_version=context.code_version,
                ),
            ],
        )

    def batch_summary(self, data_root: Path, batch_id: str) -> dict | None:
        manifest_path = reconciled_pair_dir(data_root, batch_id) / "manifest.json"
        if not manifest_path.is_file():
            return None
        return json.loads(manifest_path.read_text(encoding="utf-8"))
