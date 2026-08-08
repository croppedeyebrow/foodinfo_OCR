"""Named dynamic partitions managed through Dagster storage."""

import dagster as dg

collection_batch_partitions = dg.DynamicPartitionsDefinition(
    name="collection_batches"
)
mfds_batch_partitions = dg.DynamicPartitionsDefinition(name="mfds_batches")
gold_version_partitions = dg.DynamicPartitionsDefinition(
    name="gold_dataset_versions"
)
