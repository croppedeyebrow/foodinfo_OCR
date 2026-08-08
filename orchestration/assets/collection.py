"""Executable intake assets over externally produced Collection batches."""

import dagster as dg

from orchestration.artifact import ArtifactReference
from orchestration.partitions import collection_batch_partitions
from orchestration.resources import ArtifactStoreResource, PipelineMetadataResource


@dg.asset(
    partitions_def=collection_batch_partitions,
    group_name="collection_intake",
    kinds={"json", "filesystem"},
    description=(
        "External Collection submission produced by Console/crawler/OCR. "
        "This asset only validates and references the accepted manifest."
    ),
)
def kurly_collection_submission(
    context: dg.AssetExecutionContext,
    artifact_store: ArtifactStoreResource,
) -> dg.Output[ArtifactReference]:
    reference = artifact_store.collection_submission_reference(
        batch_id=context.partition_key
    )
    return dg.Output(
        reference,
        metadata=reference.materialization_metadata(),
    )


@dg.asset(
    partitions_def=collection_batch_partitions,
    group_name="collection_intake",
    kinds={"postgres", "json"},
    retry_policy=dg.RetryPolicy(
        max_retries=2,
        delay=1,
        backoff=dg.Backoff.EXPONENTIAL,
    ),
    description=(
        "Registers the accepted Collection bundle in pipeline metadata. "
        "Business validation remains in apps/normalizer."
    ),
)
def kurly_bronze_validated(
    context: dg.AssetExecutionContext,
    kurly_collection_submission: ArtifactReference,
    artifact_store: ArtifactStoreResource,
    pipeline_metadata: PipelineMetadataResource,
) -> dg.Output[ArtifactReference]:
    member = artifact_store.accepted_member(context.partition_key)
    reference = pipeline_metadata.register_collection_submission(
        batch_id=context.partition_key,
        member=member,
    )
    return dg.Output(
        reference,
        metadata=reference.materialization_metadata(),
    )
