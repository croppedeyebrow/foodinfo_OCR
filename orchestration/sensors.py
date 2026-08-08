"""Sensors that bridge immutable accepted batches into Dagster partitions."""

import dagster as dg

from orchestration.jobs import process_collection_batch
from orchestration.partitions import collection_batch_partitions
from orchestration.resources import ArtifactStoreResource


@dg.sensor(
    job=process_collection_batch,
    minimum_interval_seconds=30,
    default_status=dg.DefaultSensorStatus.STOPPED,
)
def accepted_collection_sensor(
    context: dg.SensorEvaluationContext,
    artifact_store: ArtifactStoreResource,
) -> dg.SensorResult | dg.SkipReason:
    known = set(
        context.instance.get_dynamic_partitions(
            collection_batch_partitions.name
        )
    )
    discovered = [
        batch_id
        for batch_id in artifact_store.accepted_batch_ids()
        if batch_id not in known
    ]
    if not discovered:
        return dg.SkipReason("No new accepted collection batches.")
    return dg.SensorResult(
        dynamic_partitions_requests=[
            collection_batch_partitions.build_add_request(discovered)
        ],
        run_requests=[
            dg.RunRequest(
                run_key=f"accepted:{batch_id}",
                partition_key=batch_id,
                tags={"batch_id": batch_id},
            )
            for batch_id in discovered
        ],
    )
