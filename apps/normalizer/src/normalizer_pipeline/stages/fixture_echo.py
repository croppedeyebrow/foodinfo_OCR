from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ...metadata.models import PipelineArtifactCreate
from ...submission import file_sha256
from .base import StageContext, StageExecutionResult, StageService

KST = ZoneInfo("Asia/Seoul")


class FixtureEchoStage:
    stage_key = "fixture_echo"
    display_name = "Fixture Echo"
    prerequisites = ("collection_accepted",)

    def check_prerequisites(self, context: StageContext) -> list[str]:
        manifest = (
            context.data_root
            / "inbox"
            / "accepted"
            / context.batch_id
            / "manifest.json"
        )
        if not manifest.is_file():
            return [
                "accepted manifest가 없습니다. 5단계 검증·제출을 먼저 완료하세요."
            ]
        return []

    def execute(self, context: StageContext) -> StageExecutionResult:
        errors = self.check_prerequisites(context)
        if errors:
            return StageExecutionResult(
                input_count=0,
                output_count=0,
                failed_count=1,
                error_code="PREREQUISITE_NOT_MET",
                error_message=errors[0],
            )

        manifest_path = (
            context.data_root
            / "inbox"
            / "accepted"
            / context.batch_id
            / "manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        output_dir = context.data_root / "pipeline" / "fixture" / context.batch_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "echo.json"
        payload = {
            "schema_version": "1.0.0",
            "batch_id": context.batch_id,
            "member": context.member,
            "source_manifest_checksum": file_sha256(manifest_path),
            "row_count": int(manifest.get("row_count") or 0),
            "generated_at": datetime.now(KST).isoformat(),
            "stage_key": self.stage_key,
            "attempt": context.attempt,
            "message": "fixture stage completed",
        }
        temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output_path)

        checksum = file_sha256(output_path)
        artifact_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{context.batch_id}:{self.stage_key}:{checksum}",
            )
        )
        return StageExecutionResult(
            input_count=1,
            output_count=1,
            failed_count=0,
            progress_message="fixture echo artifact 생성 완료",
            artifacts=[
                PipelineArtifactCreate(
                    artifact_id=artifact_id,
                    run_id="pending",
                    step_key=self.stage_key,
                    step_attempt=context.attempt,
                    logical_name="fixture_echo",
                    path=output_path.as_posix(),
                    format="JSON",
                    schema_version="1.0.0",
                    checksum=checksum,
                    row_count=1,
                    byte_size=output_path.stat().st_size,
                    code_version=context.code_version,
                )
            ],
        )
