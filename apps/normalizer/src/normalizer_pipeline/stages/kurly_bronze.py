from __future__ import annotations

import json
import uuid
from pathlib import Path

from ...kurly_transform import run_kurly_bronze
from ...metadata.models import PipelineArtifactCreate
from ...storage_paths import accepted_inbox_dir, bronze_batch_dir
from ...submission import file_sha256
from .base import StageContext, StageExecutionResult, StageService


class KurlyBronzeStage:
    stage_key = "kurly_bronze"
    display_name = "Kurly Bronze"
    prerequisites = ("collection_accepted",)

    def check_prerequisites(self, context: StageContext) -> list[str]:
        manifest = accepted_inbox_dir(context.data_root, context.batch_id) / "manifest.json"
        if not manifest.is_file():
            return [
                "accepted manifest가 없습니다. 5단계 검증·제출을 먼저 완료하세요."
            ]
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ["accepted manifest JSON이 손상되었습니다."]
        if str(payload.get("status", "")).upper() != "ACCEPTED":
            return ["accepted manifest 상태가 ACCEPTED가 아닙니다."]
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
            result = run_kurly_bronze(
                data_root=context.data_root,
                batch_id=context.batch_id,
                run_id=context.run_id or f"batch:{context.batch_id}:{self.stage_key}",
                code_version=context.code_version,
                attempt=context.attempt,
            )
        except Exception as error:
            return StageExecutionResult(
                failed_count=1,
                error_code="BRONZE_STAGE_FAILED",
                error_message=str(error),
            )

        checksum = file_sha256(result.manifest_path)
        artifact_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{context.batch_id}:{self.stage_key}:{checksum}",
            )
        )
        if result.valid_count <= 0:
            return StageExecutionResult(
                input_count=result.input_count,
                output_count=0,
                failed_count=result.quarantine_count or result.input_count,
                error_code="BRONZE_NO_VALID_RECORDS",
                error_message="Bronze로 승격된 유효 레코드가 없습니다.",
            )
        return StageExecutionResult(
            input_count=result.input_count,
            output_count=result.valid_count,
            failed_count=0,
            progress_message=(
                f"Bronze 입력 {result.input_count}건 · 정상 {result.valid_count}건 · "
                f"격리 {result.quarantine_count}건"
            ),
            artifacts=[
                PipelineArtifactCreate(
                    artifact_id=artifact_id,
                    run_id="pending",
                    step_key=self.stage_key,
                    step_attempt=context.attempt,
                    logical_name="kurly_bronze_manifest",
                    path=result.manifest_path.as_posix(),
                    format="JSON",
                    schema_version="1.0.0",
                    checksum=checksum,
                    row_count=result.valid_count,
                    byte_size=result.manifest_path.stat().st_size,
                    code_version=context.code_version,
                ),
                PipelineArtifactCreate(
                    artifact_id=str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"{context.batch_id}:{self.stage_key}:products:{checksum}",
                        )
                    ),
                    run_id="pending",
                    step_key=self.stage_key,
                    step_attempt=context.attempt,
                    logical_name="kurly_bronze_products",
                    path=result.products_path.as_posix(),
                    format="PARQUET",
                    schema_version="1.0.0",
                    checksum=file_sha256(result.products_path),
                    row_count=result.valid_count,
                    byte_size=result.products_path.stat().st_size,
                    code_version=context.code_version,
                ),
            ],
        )

    def batch_summary(self, data_root: Path, batch_id: str) -> dict | None:
        manifest_path = bronze_batch_dir(data_root, "kurly", batch_id) / "manifest.json"
        if not manifest_path.is_file():
            return None
        return json.loads(manifest_path.read_text(encoding="utf-8"))
