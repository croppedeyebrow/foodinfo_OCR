from __future__ import annotations

import json
import uuid
from pathlib import Path

from ...gold_transform import GoldDatasetVersionExistsError, run_gold_freshness_publish
from ...metadata.models import PipelineArtifactCreate
from ...storage_paths import gold_freshness_profiles_dir, reconciled_pair_dir
from ...submission import file_sha256
from .base import StageContext, StageExecutionResult, StageService


class GoldFreshnessPublishStage:
    stage_key = "gold_freshness_publish"
    display_name = "Gold Publish"
    prerequisites = ("kurly_kfia_reconcile",)

    def check_prerequisites(self, context: StageContext) -> list[str]:
        reconcile_manifest = reconciled_pair_dir(context.data_root, context.batch_id) / "manifest.json"
        if not reconcile_manifest.is_file():
            return ["Reconciled manifest가 없습니다. Kurly–KFIA 대조를 먼저 실행하세요."]
        gold_manifest = (
            gold_freshness_profiles_dir(context.data_root, context.batch_id) / "manifest.json"
        )
        if gold_manifest.is_file():
            return [
                f"Gold bundle이 이미 존재합니다 (dataset_version={context.batch_id}). "
                "중복 생성할 수 없습니다."
            ]
        try:
            payload = json.loads(reconcile_manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ["Reconciled manifest JSON이 손상되었습니다."]
        if int(payload.get("approved_count") or 0) <= 0:
            return ["승인된 대조 레코드가 없어 Gold를 생성할 수 없습니다."]
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
            result = run_gold_freshness_publish(
                data_root=context.data_root,
                pair_id=context.batch_id,
                run_id=context.run_id or f"batch:{context.batch_id}:{self.stage_key}",
                code_version=context.code_version,
                attempt=context.attempt,
            )
        except GoldDatasetVersionExistsError as error:
            return StageExecutionResult(
                failed_count=1,
                error_code="GOLD_VERSION_EXISTS",
                error_message=str(error),
            )
        except Exception as error:
            return StageExecutionResult(
                failed_count=1,
                error_code="GOLD_PUBLISH_FAILED",
                error_message=str(error),
            )

        checksum = file_sha256(result.manifest_path)
        return StageExecutionResult(
            input_count=result.input_count,
            output_count=result.record_count,
            failed_count=0,
            progress_message=(
                f"Gold 입력 {result.input_count}건 · 승인 {result.approved_input_count}건 · "
                f"제외 {result.excluded_count}건 · lineage 연결 {result.lineage_linked_count}건"
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
                    logical_name="gold_freshness_manifest",
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
                    logical_name="gold_freshness_profiles",
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
        manifest_path = gold_freshness_profiles_dir(data_root, batch_id) / "manifest.json"
        if not manifest_path.is_file():
            return None
        return json.loads(manifest_path.read_text(encoding="utf-8"))
