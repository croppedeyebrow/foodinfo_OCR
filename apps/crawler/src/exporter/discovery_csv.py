from __future__ import annotations

import csv
from pathlib import Path

from ..models import DiscoveredProduct


DISCOVERY_COLUMNS = [
    "schema_version",
    "batch_id",
    "source_site",
    "source_mode",
    "source_value",
    "original_product_id",
    "product_name_preview",
    "product_url",
    "discovery_order",
    "discovered_at",
    "discovery_status",
]


def write_discovery_csv(products: list[DiscoveredProduct], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=DISCOVERY_COLUMNS)
        writer.writeheader()
        for product in products:
            payload = product.model_dump(mode="json")
            writer.writerow({column: payload.get(column, "") for column in DISCOVERY_COLUMNS})
    return output_path
