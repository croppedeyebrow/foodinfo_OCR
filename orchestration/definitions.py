"""Dagster code location for the NaengLog data platform."""

import os

import dagster as dg

from orchestration.assets import (
    FUTURE_ASSET_SPECS,
    kurly_bronze_validated,
    kurly_collection_submission,
)
from orchestration.jobs import ALL_JOBS
from orchestration.resources import (
    ArtifactStoreResource,
    DuckDBResource,
    PipelineMetadataResource,
)
from orchestration.sensors import accepted_collection_sensor

defs = dg.Definitions(
    assets=[
        kurly_collection_submission,
        kurly_bronze_validated,
        *FUTURE_ASSET_SPECS,
    ],
    jobs=ALL_JOBS,
    sensors=[accepted_collection_sensor],
    resources={
        "artifact_store": ArtifactStoreResource(
            data_root=os.getenv("DATA_ROOT", "/data"),
            contracts_dir=os.getenv("CONTRACTS_DIR", "/app/contracts"),
        ),
        "pipeline_metadata": PipelineMetadataResource(
            database_url=dg.EnvVar("DATABASE_URL"),
            data_root=os.getenv("DATA_ROOT", "/data"),
            contracts_dir=os.getenv("CONTRACTS_DIR", "/app/contracts"),
            code_version=os.getenv("PIPELINE_CODE_VERSION", "dev"),
        ),
        "duckdb": DuckDBResource(
            database_path=os.getenv(
                "DUCKDB_PATH", "/data/warehouse/pipeline.duckdb"
            )
        ),
    },
)
