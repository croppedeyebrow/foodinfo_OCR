from __future__ import annotations

import json
import uuid
from pathlib import Path

from ...kfia_transform import run_kfia_silver
from ...metadata.models import PipelineArtifactCreate
from ...storage_paths import bronze_batch_dir, silver_batch_dir
from ...submission import file_sha256
from .base import StageContext, StageExecutionResult, StageService


class KfiaReferenceSilverStage:
    stage_key = "kfia_reference_silver"
    display_name = "Reference Silver"
    prerequisites = ("kfia_reference_bronze",)

    def check_prerequisites(self, context: StageContext) -> list[str]:
        manifest_path = bronze_batch_dir(context.data_root, "kfia", context.batch_id) / "manifest.json"
        if not manifest_path.is_file():
            return ["Reference Bronze manifest가 없습니다. Reference Bronze를 먼저 실행하세요."]
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ["Reference Bronze manifest JSON이 손상되었습니다."]
        if int(payload.get("valid_count") or 0) <= 0:
            return ["Reference Bronze에 유효 레코드가 없습니다."]
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
            result = run_kfia_silver(
                data_root=context.data_root,
                dataset_version=context.batch_id,
                run_id=context.run_id or f"batch:{context.batch_id}:{self.stage_key}",
                code_version=context.code_version,
                attempt=context.attempt,
            )
        except Exception as error:
            return StageExecutionResult(
                failed_count=1,
                error_code="KFIA_SILVER_STAGE_FAILED",
                error_message=str(error),
            )

        checksum = file_sha256(result.manifest_path)
        return StageExecutionResult(
            input_count=result.input_count,
            output_count=result.record_count,
            failed_count=0,
            progress_message=(
                f"Reference Silver 입력 {result.input_count}건 · 승인 {result.approved_count}건 · "
                f"검토 {result.review_required_count}건 · 거절 {result.rejected_count}건"
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
                    logical_name="kfia_reference_silver_manifest",
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
                    logical_name="kfia_reference_silver_records",
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
        manifest_path = silver_batch_dir(data_root, "kfia", batch_id) / "manifest.json"
        if not manifest_path.is_file():
            return None
        return json.loads(manifest_path.read_text(encoding="utf-8"))
