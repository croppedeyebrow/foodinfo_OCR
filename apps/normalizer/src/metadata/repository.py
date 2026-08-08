"""PostgreSQL repository for pipeline execution metadata only."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .models import (
    ArtifactLineageCreate,
    PipelineArtifactCreate,
    PipelineRunCreate,
    PipelineStepCreate,
    QualityResultCreate,
    RunStatus,
    validate_status_transition,
)


class MetadataConflictError(RuntimeError):
    pass


def _enum_value(value: object) -> object:
    return value.value if hasattr(value, "value") else value


class MetadataRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.database_url, row_factory=dict_row)

    def create_run(self, record: PipelineRunCreate) -> dict[str, Any]:
        values = record.model_dump(mode="json")
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO pipeline_metadata.pipeline_runs (
                    run_id, pipeline_name, batch_id, trigger_type, status,
                    started_at, finished_at, code_version, config_hash,
                    error_summary, log_path
                )
                VALUES (
                    %(run_id)s, %(pipeline_name)s, %(batch_id)s, %(trigger_type)s,
                    %(status)s, %(started_at)s, %(finished_at)s, %(code_version)s,
                    %(config_hash)s, %(error_summary)s, %(log_path)s
                )
                ON CONFLICT (run_id) DO NOTHING
                RETURNING *
                """,
                values,
            ).fetchone()
            if row is not None:
                return dict(row)
            existing = connection.execute(
                """
                SELECT * FROM pipeline_metadata.pipeline_runs WHERE run_id = %s
                """,
                (record.run_id,),
            ).fetchone()
            assert existing is not None
            for key in (
                "pipeline_name",
                "batch_id",
                "trigger_type",
                "code_version",
                "config_hash",
            ):
                if existing[key] != values[key]:
                    raise MetadataConflictError(
                        f"run_id conflict for {record.run_id}: field={key}"
                    )
            return dict(existing)

    def transition_run(
        self,
        run_id: str,
        target: RunStatus,
        *,
        at: datetime | None = None,
        error_summary: str | None = None,
        log_path: str | None = None,
    ) -> dict[str, Any]:
        target_status = RunStatus(_enum_value(target))
        with self._connect() as connection:
            current = connection.execute(
                """
                SELECT status FROM pipeline_metadata.pipeline_runs
                WHERE run_id = %s FOR UPDATE
                """,
                (run_id,),
            ).fetchone()
            if current is None:
                raise KeyError(f"run not found: {run_id}")
            validate_status_transition(RunStatus(current["status"]), target_status)
            row = connection.execute(
                """
                UPDATE pipeline_metadata.pipeline_runs
                SET status = %(status)s,
                    started_at = CASE
                        WHEN %(status)s = 'RUNNING'
                            THEN COALESCE(started_at, %(at)s, CURRENT_TIMESTAMP)
                        ELSE started_at
                    END,
                    finished_at = CASE
                        WHEN %(status)s IN (
                            'SUCCEEDED', 'FAILED', 'PARTIAL', 'CANCELLED'
                        ) THEN COALESCE(%(at)s, CURRENT_TIMESTAMP)
                        ELSE finished_at
                    END,
                    error_summary = COALESCE(%(error_summary)s, error_summary),
                    log_path = COALESCE(%(log_path)s, log_path),
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = %(run_id)s
                RETURNING *
                """,
                {
                    "run_id": run_id,
                    "status": target_status.value,
                    "at": at,
                    "error_summary": error_summary,
                    "log_path": log_path,
                },
            ).fetchone()
            assert row is not None
            return dict(row)

    def create_step(self, record: PipelineStepCreate) -> dict[str, Any]:
        values = record.model_dump(mode="json")
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO pipeline_metadata.pipeline_steps (
                    run_id, step_key, attempt, status, started_at, finished_at,
                    input_count, output_count, failed_count, error_code,
                    error_message, log_path
                )
                VALUES (
                    %(run_id)s, %(step_key)s, %(attempt)s, %(status)s,
                    %(started_at)s, %(finished_at)s, %(input_count)s,
                    %(output_count)s, %(failed_count)s, %(error_code)s,
                    %(error_message)s, %(log_path)s
                )
                ON CONFLICT (run_id, step_key, attempt) DO NOTHING
                RETURNING *
                """,
                values,
            ).fetchone()
            if row is not None:
                return dict(row)
            existing = connection.execute(
                """
                SELECT * FROM pipeline_metadata.pipeline_steps
                WHERE run_id = %s AND step_key = %s AND attempt = %s
                """,
                (record.run_id, record.step_key, record.attempt),
            ).fetchone()
            assert existing is not None
            return dict(existing)

    def transition_step(
        self,
        run_id: str,
        step_key: str,
        attempt: int,
        target: RunStatus,
        *,
        at: datetime | None = None,
        input_count: int | None = None,
        output_count: int | None = None,
        failed_count: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        log_path: str | None = None,
    ) -> dict[str, Any]:
        target_status = RunStatus(_enum_value(target))
        counts = (input_count, output_count, failed_count)
        if any(value is not None and value < 0 for value in counts):
            raise ValueError("step counts must be non-negative")
        with self._connect() as connection:
            current = connection.execute(
                """
                SELECT status FROM pipeline_metadata.pipeline_steps
                WHERE run_id = %s AND step_key = %s AND attempt = %s
                FOR UPDATE
                """,
                (run_id, step_key, attempt),
            ).fetchone()
            if current is None:
                raise KeyError(f"step not found: {run_id}/{step_key}/{attempt}")
            validate_status_transition(RunStatus(current["status"]), target_status)
            row = connection.execute(
                """
                UPDATE pipeline_metadata.pipeline_steps
                SET status = %(status)s,
                    started_at = CASE
                        WHEN %(status)s = 'RUNNING'
                            THEN COALESCE(started_at, %(at)s, CURRENT_TIMESTAMP)
                        ELSE started_at
                    END,
                    finished_at = CASE
                        WHEN %(status)s IN (
                            'SUCCEEDED', 'FAILED', 'PARTIAL', 'CANCELLED'
                        ) THEN COALESCE(%(at)s, CURRENT_TIMESTAMP)
                        ELSE finished_at
                    END,
                    input_count = COALESCE(%(input_count)s, input_count),
                    output_count = COALESCE(%(output_count)s, output_count),
                    failed_count = COALESCE(%(failed_count)s, failed_count),
                    error_code = COALESCE(%(error_code)s, error_code),
                    error_message = COALESCE(%(error_message)s, error_message),
                    log_path = COALESCE(%(log_path)s, log_path),
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = %(run_id)s
                  AND step_key = %(step_key)s
                  AND attempt = %(attempt)s
                RETURNING *
                """,
                {
                    "run_id": run_id,
                    "step_key": step_key,
                    "attempt": attempt,
                    "status": target_status.value,
                    "at": at,
                    "input_count": input_count,
                    "output_count": output_count,
                    "failed_count": failed_count,
                    "error_code": error_code,
                    "error_message": error_message,
                    "log_path": log_path,
                },
            ).fetchone()
            assert row is not None
            return dict(row)

    def register_artifact(
        self, record: PipelineArtifactCreate
    ) -> dict[str, Any]:
        values = record.model_dump(mode="json")
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO pipeline_metadata.pipeline_artifacts (
                    artifact_id, run_id, step_key, step_attempt, logical_name,
                    path, format, schema_version, checksum, row_count, byte_size,
                    code_version, rule_version
                )
                VALUES (
                    %(artifact_id)s, %(run_id)s, %(step_key)s, %(step_attempt)s,
                    %(logical_name)s, %(path)s, %(format)s, %(schema_version)s,
                    %(checksum)s, %(row_count)s, %(byte_size)s, %(code_version)s,
                    %(rule_version)s
                )
                ON CONFLICT DO NOTHING
                RETURNING *
                """,
                values,
            ).fetchone()
            if row is not None:
                return dict(row)
            existing = connection.execute(
                """
                SELECT * FROM pipeline_metadata.pipeline_artifacts
                WHERE run_id = %(run_id)s
                  AND step_key = %(step_key)s
                  AND step_attempt = %(step_attempt)s
                  AND logical_name = %(logical_name)s
                  AND checksum = %(checksum)s
                """,
                values,
            ).fetchone()
            if existing is None:
                raise MetadataConflictError(
                    f"artifact_id conflict: {record.artifact_id}"
                )
            return dict(existing)

    def add_lineage(self, record: ArtifactLineageCreate) -> dict[str, Any]:
        values = record.model_dump(mode="json")
        with self._connect() as connection:
            cycle = connection.execute(
                """
                WITH RECURSIVE descendants(artifact_id) AS (
                    SELECT child_artifact_id
                    FROM pipeline_metadata.pipeline_artifact_lineage
                    WHERE parent_artifact_id = %(child_artifact_id)s
                    UNION
                    SELECT lineage.child_artifact_id
                    FROM pipeline_metadata.pipeline_artifact_lineage AS lineage
                    JOIN descendants
                      ON lineage.parent_artifact_id = descendants.artifact_id
                )
                SELECT 1
                FROM descendants
                WHERE artifact_id = %(parent_artifact_id)s
                LIMIT 1
                """,
                values,
            ).fetchone()
            if cycle is not None:
                raise ValueError(
                    "artifact lineage cycle rejected: "
                    f"{record.parent_artifact_id} -> {record.child_artifact_id}"
                )
            row = connection.execute(
                """
                INSERT INTO pipeline_metadata.pipeline_artifact_lineage (
                    parent_artifact_id, child_artifact_id, relation_type
                )
                VALUES (
                    %(parent_artifact_id)s, %(child_artifact_id)s,
                    %(relation_type)s
                )
                ON CONFLICT (
                    parent_artifact_id, child_artifact_id, relation_type
                ) DO UPDATE SET relation_type = EXCLUDED.relation_type
                RETURNING *
                """,
                values,
            ).fetchone()
            assert row is not None
            return dict(row)

    def record_quality_result(
        self, record: QualityResultCreate
    ) -> dict[str, Any]:
        values = record.model_dump(mode="json")
        values["details"] = json.dumps(values["details"], ensure_ascii=False)
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO pipeline_metadata.quality_results (
                    quality_result_id, run_id, artifact_id, rule_id, severity,
                    passed, observed_value, details
                )
                VALUES (
                    %(quality_result_id)s, %(run_id)s, %(artifact_id)s,
                    %(rule_id)s, %(severity)s, %(passed)s, %(observed_value)s,
                    %(details)s::jsonb
                )
                ON CONFLICT (run_id, artifact_id, rule_id)
                DO UPDATE SET
                    severity = EXCLUDED.severity,
                    passed = EXCLUDED.passed,
                    observed_value = EXCLUDED.observed_value,
                    details = EXCLUDED.details
                RETURNING *
                """,
                values,
            ).fetchone()
            assert row is not None
            return dict(row)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            run = connection.execute(
                "SELECT * FROM pipeline_metadata.pipeline_runs WHERE run_id = %s",
                (run_id,),
            ).fetchone()
            if run is None:
                return None
            steps = connection.execute(
                """
                SELECT * FROM pipeline_metadata.pipeline_steps
                WHERE run_id = %s ORDER BY step_key, attempt
                """,
                (run_id,),
            ).fetchall()
            artifacts = connection.execute(
                """
                SELECT * FROM pipeline_metadata.pipeline_artifacts
                WHERE run_id = %s ORDER BY step_key, logical_name
                """,
                (run_id,),
            ).fetchall()
            quality = connection.execute(
                """
                SELECT * FROM pipeline_metadata.quality_results
                WHERE run_id = %s ORDER BY artifact_id, rule_id
                """,
                (run_id,),
            ).fetchall()
            return {
                "run": dict(run),
                "steps": [dict(item) for item in steps],
                "artifacts": [dict(item) for item in artifacts],
                "quality_results": [dict(item) for item in quality],
            }

    def list_runs(
        self, *, batch_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self._connect() as connection:
            if batch_id is None:
                rows = connection.execute(
                    """
                    SELECT * FROM pipeline_metadata.pipeline_runs
                    ORDER BY created_at DESC LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM pipeline_metadata.pipeline_runs
                    WHERE batch_id = %s
                    ORDER BY created_at DESC LIMIT %s
                    """,
                    (batch_id, limit),
                ).fetchall()
            return [dict(item) for item in rows]

    def trace_ancestors(self, artifact_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                WITH RECURSIVE ancestors AS (
                    SELECT
                        lineage.parent_artifact_id,
                        lineage.child_artifact_id,
                        lineage.relation_type,
                        1 AS depth
                    FROM pipeline_metadata.pipeline_artifact_lineage AS lineage
                    WHERE lineage.child_artifact_id = %s
                    UNION ALL
                    SELECT
                        lineage.parent_artifact_id,
                        lineage.child_artifact_id,
                        lineage.relation_type,
                        ancestors.depth + 1
                    FROM pipeline_metadata.pipeline_artifact_lineage AS lineage
                    JOIN ancestors
                      ON lineage.child_artifact_id = ancestors.parent_artifact_id
                )
                SELECT DISTINCT
                    artifacts.*,
                    ancestors.child_artifact_id,
                    ancestors.relation_type,
                    ancestors.depth
                FROM ancestors
                JOIN pipeline_metadata.pipeline_artifacts AS artifacts
                  ON artifacts.artifact_id = ancestors.parent_artifact_id
                ORDER BY ancestors.depth, artifacts.artifact_id
                """,
                (artifact_id,),
            ).fetchall()
            return [dict(item) for item in rows]
