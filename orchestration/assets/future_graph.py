"""Non-materializable contracts for assets implemented in later stages."""

import dagster as dg

from orchestration.partitions import (
    collection_batch_partitions,
    gold_version_partitions,
    mfds_batch_partitions,
)


def _future_spec(
    key: str,
    *,
    deps: list[str],
    group_name: str,
    implementation_stage: str,
    partitions_def: dg.PartitionsDefinition | None = None,
) -> dg.AssetSpec:
    return dg.AssetSpec(
        key=key,
        deps=deps,
        group_name=group_name,
        partitions_def=partitions_def,
        metadata={
            "implementation_status": "external_until_stage",
            "implementation_stage": implementation_stage,
        },
        description=(
            f"Graph contract only. Materialization is introduced by "
            f"{implementation_stage}; stage 05 does not fabricate this artifact."
        ),
    )


FUTURE_ASSET_SPECS = [
    _future_spec(
        "kurly_silver_freshness",
        deps=["kurly_bronze_validated"],
        group_name="transformation",
        implementation_stage="stage_06",
        partitions_def=collection_batch_partitions,
    ),
    _future_spec(
        "mfds_source_pdf",
        deps=[],
        group_name="mfds_reference",
        implementation_stage="stage_07",
        partitions_def=mfds_batch_partitions,
    ),
    _future_spec(
        "mfds_bronze_records",
        deps=["mfds_source_pdf"],
        group_name="mfds_reference",
        implementation_stage="stage_07",
        partitions_def=mfds_batch_partitions,
    ),
    _future_spec(
        "mfds_silver_freshness",
        deps=["mfds_bronze_records"],
        group_name="transformation",
        implementation_stage="stage_07",
        partitions_def=mfds_batch_partitions,
    ),
    _future_spec(
        "reconciled_freshness",
        deps=["kurly_silver_freshness", "mfds_silver_freshness"],
        group_name="reconciliation",
        implementation_stage="stage_07",
    ),
    _future_spec(
        "freshness_quality_checked",
        deps=["reconciled_freshness"],
        group_name="quality",
        implementation_stage="stage_08",
    ),
    _future_spec(
        "gold_freshness_profiles",
        deps=["freshness_quality_checked"],
        group_name="publication",
        implementation_stage="stage_10",
        partitions_def=gold_version_partitions,
    ),
    _future_spec(
        "backend_export_bundle",
        deps=["gold_freshness_profiles"],
        group_name="publication",
        implementation_stage="stage_10",
        partitions_def=gold_version_partitions,
    ),
]
