"""Asset jobs exposed to platform operators."""

import dagster as dg

from orchestration.assets import (
    kurly_bronze_validated,
    kurly_collection_submission,
)

process_collection_batch = dg.define_asset_job(
    name="process_collection_batch",
    selection=dg.AssetSelection.assets(
        kurly_collection_submission,
        kurly_bronze_validated,
    ),
    description="Validate and register one accepted collection batch partition.",
)

def _future_job(name: str, stage: str) -> dg.JobDefinition:
    @dg.op(name=f"{name}_implementation_gate")
    def implementation_gate() -> None:
        raise dg.Failure(
            f"{name} is a graph contract and becomes executable in {stage}."
        )

    @dg.job(
        name=name,
        description=(
            f"Reserved operator job. It fails fast until {stage} provides "
            "materializable application assets."
        ),
        tags={
            "implementation_status": "blocked",
            "implementation_stage": stage,
        },
    )
    def reserved_job() -> None:
        implementation_gate()

    return reserved_job


refresh_mfds_reference = _future_job("refresh_mfds_reference", "stage_07")
rebuild_reconciliation = _future_job("rebuild_reconciliation", "stage_07")
publish_gold_dataset = _future_job("publish_gold_dataset", "stage_10")

ALL_JOBS = [
    process_collection_batch,
    refresh_mfds_reference,
    rebuild_reconciliation,
    publish_gold_dataset,
]

__all__ = [
    "ALL_JOBS",
    "process_collection_batch",
    "publish_gold_dataset",
    "rebuild_reconciliation",
    "refresh_mfds_reference",
]
