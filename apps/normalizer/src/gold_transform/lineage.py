from __future__ import annotations

from typing import Any


def build_lineage_chain(
    *,
    gold_record_id: str,
    external_product_id: str,
    pair_id: str,
    kurly_batch_id: str,
    kfia_dataset_version: str,
    reconciled_record_id: str,
    kurly_silver_record_id: str,
    kurly_bronze_record_id: str | None,
    kfia_silver_record_id: str | None,
    kfia_bronze_record_id: str | None,
) -> dict[str, Any]:
    chain: list[dict[str, str]] = [
        {
            "layer": "gold",
            "record_id": gold_record_id,
            "artifact": "freshness_profiles.parquet",
            "dataset_version": pair_id,
        },
        {
            "layer": "reconciled",
            "record_id": reconciled_record_id,
            "pair_id": pair_id,
            "artifact": "records.parquet",
        },
        {
            "layer": "kurly_silver",
            "record_id": kurly_silver_record_id,
            "batch_id": kurly_batch_id,
            "artifact": "products.parquet",
        },
    ]
    if kurly_bronze_record_id:
        chain.append(
            {
                "layer": "kurly_bronze",
                "record_id": kurly_bronze_record_id,
                "batch_id": kurly_batch_id,
                "artifact": "products.parquet",
            }
        )
        chain.append(
            {
                "layer": "accepted",
                "batch_id": kurly_batch_id,
                "artifact": "submission manifest",
            }
        )
    if kfia_silver_record_id:
        chain.append(
            {
                "layer": "kfia_silver",
                "record_id": kfia_silver_record_id,
                "dataset_version": kfia_dataset_version,
                "artifact": "records.parquet",
            }
        )
    if kfia_bronze_record_id:
        chain.append(
            {
                "layer": "kfia_bronze",
                "record_id": kfia_bronze_record_id,
                "dataset_version": kfia_dataset_version,
                "artifact": "records.parquet",
            }
        )
        chain.append(
            {
                "layer": "reference_inbox",
                "dataset_version": kfia_dataset_version,
                "artifact": "manifest.json",
            }
        )
    return {
        "gold_record_id": gold_record_id,
        "external_product_id": external_product_id,
        "pair_id": pair_id,
        "chain": chain,
        "lineage_complete": kurly_bronze_record_id is not None
        and (kfia_silver_record_id is None or kfia_bronze_record_id is not None),
    }
