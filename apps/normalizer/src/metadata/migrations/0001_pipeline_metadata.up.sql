CREATE TABLE pipeline_metadata.pipeline_runs (
    run_id TEXT PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    batch_id TEXT,
    trigger_type TEXT NOT NULL CHECK (
        trigger_type IN ('MANUAL', 'CONSOLE', 'DAGSTER', 'SCHEDULE', 'EXTERNAL_SUBMISSION')
    ),
    status TEXT NOT NULL CHECK (
        status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'PARTIAL', 'CANCELLED')
    ),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL CHECK (config_hash ~ '^[a-f0-9]{64}$'),
    error_summary TEXT CHECK (
        error_summary IS NULL OR octet_length(error_summary) <= 16384
    ),
    log_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX pipeline_runs_batch_idx
    ON pipeline_metadata.pipeline_runs (batch_id, created_at DESC);
CREATE INDEX pipeline_runs_status_idx
    ON pipeline_metadata.pipeline_runs (status, created_at DESC);

CREATE TABLE pipeline_metadata.pipeline_steps (
    run_id TEXT NOT NULL REFERENCES pipeline_metadata.pipeline_runs(run_id)
        ON DELETE CASCADE,
    step_key TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt >= 1),
    status TEXT NOT NULL CHECK (
        status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'PARTIAL', 'CANCELLED')
    ),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    input_count BIGINT NOT NULL DEFAULT 0 CHECK (input_count >= 0),
    output_count BIGINT NOT NULL DEFAULT 0 CHECK (output_count >= 0),
    failed_count BIGINT NOT NULL DEFAULT 0 CHECK (failed_count >= 0),
    error_code TEXT,
    error_message TEXT CHECK (
        error_message IS NULL OR octet_length(error_message) <= 16384
    ),
    log_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, step_key, attempt),
    CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX pipeline_steps_status_idx
    ON pipeline_metadata.pipeline_steps (status, updated_at DESC);

CREATE TABLE pipeline_metadata.pipeline_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_key TEXT NOT NULL,
    step_attempt INTEGER NOT NULL DEFAULT 1,
    logical_name TEXT NOT NULL,
    path TEXT NOT NULL,
    format TEXT NOT NULL,
    schema_version TEXT,
    checksum TEXT NOT NULL CHECK (checksum ~ '^[a-f0-9]{64}$'),
    row_count BIGINT CHECK (row_count IS NULL OR row_count >= 0),
    byte_size BIGINT NOT NULL CHECK (byte_size >= 0),
    code_version TEXT NOT NULL,
    rule_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id, step_key, step_attempt)
        REFERENCES pipeline_metadata.pipeline_steps(run_id, step_key, attempt)
        ON DELETE CASCADE,
    UNIQUE (run_id, step_key, step_attempt, logical_name, checksum)
);

CREATE INDEX pipeline_artifacts_checksum_idx
    ON pipeline_metadata.pipeline_artifacts (checksum);
CREATE INDEX pipeline_artifacts_run_idx
    ON pipeline_metadata.pipeline_artifacts (run_id, step_key);

CREATE TABLE pipeline_metadata.pipeline_artifact_lineage (
    parent_artifact_id TEXT NOT NULL
        REFERENCES pipeline_metadata.pipeline_artifacts(artifact_id) ON DELETE CASCADE,
    child_artifact_id TEXT NOT NULL
        REFERENCES pipeline_metadata.pipeline_artifacts(artifact_id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL DEFAULT 'DERIVED_FROM',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (parent_artifact_id, child_artifact_id, relation_type),
    CHECK (parent_artifact_id <> child_artifact_id)
);

CREATE INDEX pipeline_artifact_lineage_child_idx
    ON pipeline_metadata.pipeline_artifact_lineage (child_artifact_id);

CREATE TABLE pipeline_metadata.quality_results (
    quality_result_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES pipeline_metadata.pipeline_runs(run_id)
        ON DELETE CASCADE,
    artifact_id TEXT NOT NULL
        REFERENCES pipeline_metadata.pipeline_artifacts(artifact_id) ON DELETE CASCADE,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'ERROR')),
    passed BOOLEAN NOT NULL,
    observed_value TEXT CHECK (
        observed_value IS NULL OR octet_length(observed_value) <= 16384
    ),
    details JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (
        jsonb_typeof(details) = 'object' AND octet_length(details::text) <= 65536
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, artifact_id, rule_id)
);

CREATE INDEX quality_results_run_idx
    ON pipeline_metadata.quality_results (run_id, passed, severity);
