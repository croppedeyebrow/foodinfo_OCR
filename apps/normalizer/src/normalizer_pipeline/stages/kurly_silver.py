from __future__ import annotations

import json
import uuid
from pathlib import Path

from ...kurly_transform import run_kurly_silver
from ...metadata.models import PipelineArtifactCreate
from ...storage_paths import bronze_batch_dir, silver_batch_dir
from ...submission import file_sha256
from .base import StageContext, StageExecutionResult, StageService


class KurlySilverStage:
    stage_key = "kurly_silver"
    display_name = "Kurly Silver"
    prerequisites = ("kurly_bronze",)

    def check_prerequisites(self, context: StageContext) -> list[str]:
        manifest = bronze_batch_dir(context.data_root, "kurly", context.batch_id) / "manifest.json"
        if not manifest.is_file():
            return ["Kurly Bronze manifest가 없습니다. Bronze Stage를 먼저 실행하세요."]
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ["Bronze manifest JSON이 손상되었습니다."]
        if int(payload.get("valid_count") or 0) <= 0:
            return ["Bronze에 유효한 레코드가 없습니다."]
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
            result = run_kurly_silver(
                data_root=context.data_root,
                batch_id=context.batch_id,
                run_id=context.run_id or f"batch:{context.batch_id}:{self.stage_key}",
                code_version=context.code_version,
                attempt=context.attempt,
            )
        except Exception as error:
            return StageExecutionResult(
                failed_count=1,
                error_code="SILVER_STAGE_FAILED",
                error_message=str(error),
            )

        checksum = file_sha256(result.manifest_path)
        return StageExecutionResult(
            input_count=result.input_count,
            output_count=result.unique_product_count,
            failed_count=0,
            progress_message=(
                f"Silver 고유상품 {result.unique_product_count}건 · 파싱성공 "
                f"{result.parse_success_count}건 · 검토필요 {result.review_required_count}건 · "
                f"evidence 보존율 {result.evidence_preservation_rate:.0%}"
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
                    logical_name="kurly_silver_manifest",
                    path=result.manifest_path.as_posix(),
                    format="JSON",
                    schema_version="1.0.0",
                    checksum=checksum,
                    row_count=result.unique_product_count,
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
                    logical_name="kurly_silver_products",
                    path=result.products_path.as_posix(),
                    format="PARQUET",
                    schema_version="1.0.0",
                    checksum=file_sha256(result.products_path),
                    row_count=result.unique_product_count,
                    byte_size=result.products_path.stat().st_size,
                    code_version=context.code_version,
                ),
                PipelineArtifactCreate(
                    artifact_id=str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"{context.batch_id}:{self.stage_key}:evidence:{checksum}",
                        )
                    ),
                    run_id="pending",
                    step_key=self.stage_key,
                    step_attempt=context.attempt,
                    logical_name="kurly_silver_evidence",
                    path=result.evidence_path.as_posix(),
                    format="JSONL",
                    schema_version="1.0.0",
                    checksum=file_sha256(result.evidence_path),
                    row_count=result.unique_product_count,
                    byte_size=result.evidence_path.stat().st_size,
                    code_version=context.code_version,
                ),
            ],
        )

    def batch_summary(self, data_root: Path, batch_id: str) -> dict | None:
        manifest_path = silver_batch_dir(data_root, "kurly", batch_id) / "manifest.json"
        if not manifest_path.is_file():
            return None
        return json.loads(manifest_path.read_text(encoding="utf-8"))
