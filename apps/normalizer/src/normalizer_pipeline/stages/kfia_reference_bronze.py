from __future__ import annotations

import json
import uuid
from pathlib import Path

from ...kfia_transform import run_kfia_bronze
from ...metadata.models import PipelineArtifactCreate
from ...reference_registration import load_reference_manifest
from ...storage_paths import bronze_batch_dir
from ...submission import file_sha256
from .base import StageContext, StageExecutionResult, StageService


class KfiaReferenceBronzeStage:
    stage_key = "kfia_reference_bronze"
    display_name = "Reference Bronze"
    prerequisites = ("reference_registered",)

    def check_prerequisites(self, context: StageContext) -> list[str]:
        manifest = load_reference_manifest(context.data_root, context.batch_id)
        if manifest is None:
            return ["KFIA reference manifest가 없습니다. 기준 파일을 먼저 등록하세요."]
        status = str(manifest.get("status", "")).upper()
        if status not in {"REGISTERED", "VALIDATED"}:
            return ["reference manifest 상태가 REGISTERED 또는 VALIDATED가 아닙니다."]
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
            result = run_kfia_bronze(
                data_root=context.data_root,
                dataset_version=context.batch_id,
                run_id=context.run_id or f"batch:{context.batch_id}:{self.stage_key}",
                code_version=context.code_version,
                attempt=context.attempt,
            )
        except Exception as error:
            return StageExecutionResult(
                failed_count=1,
                error_code="KFIA_BRONZE_STAGE_FAILED",
                error_message=str(error),
            )

        checksum = file_sha256(result.manifest_path)
        if result.valid_count <= 0:
            return StageExecutionResult(
                input_count=result.input_count,
                output_count=0,
                failed_count=result.quarantine_count or result.input_count,
                error_code="BRONZE_NO_VALID_RECORDS",
                error_message="Reference Bronze로 승격된 유효 레코드가 없습니다.",
            )
        return StageExecutionResult(
            input_count=result.input_count,
            output_count=result.valid_count,
            failed_count=result.quarantine_count,
            progress_message=(
                f"Reference Bronze 입력 {result.input_count}건 · 정상 {result.valid_count}건 · "
                f"격리 {result.quarantine_count}건"
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
                    logical_name="kfia_reference_bronze_manifest",
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
                            f"{context.batch_id}:{self.stage_key}:records:{checksum}",
                        )
                    ),
                    run_id="pending",
                    step_key=self.stage_key,
                    step_attempt=context.attempt,
                    logical_name="kfia_reference_bronze_records",
                    path=result.records_path.as_posix(),
                    format="PARQUET",
                    schema_version="1.0.0",
                    checksum=file_sha256(result.records_path),
                    row_count=result.valid_count,
                    byte_size=result.records_path.stat().st_size,
                    code_version=context.code_version,
                ),
            ],
        )

    def batch_summary(self, data_root: Path, batch_id: str) -> dict | None:
        manifest_path = bronze_batch_dir(data_root, "kfia", batch_id) / "manifest.json"
        if not manifest_path.is_file():
            return None
        return json.loads(manifest_path.read_text(encoding="utf-8"))
