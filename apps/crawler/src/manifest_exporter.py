from __future__ import annotations

import csv
from pathlib import Path

from .models import CrawlFailureRecord, CrawledProductRecord, ManifestRow


MANIFEST_COLUMNS = [
    "batch_id",
    "original_product_id",
    "product_name",
    "product_url",
    "image_path",
    "source_image_url",
    "source_site",
    "expiration_info_dom",
    "storage_method_dom",
    "storage_type_dom",
    "food_name_candidate",
    "weight_raw",
    "quantity_raw",
    "sales_unit_raw",
]

FAILURE_COLUMNS = list(CrawlFailureRecord.model_fields)


def build_manifest_rows(record: CrawledProductRecord) -> list[ManifestRow]:
    base = {
        "batch_id": record.batch_id,
        "original_product_id": record.original_product_id,
        "product_name": record.product_name_raw or "",
        "product_url": record.product_url,
        "source_site": record.source_site,
        "expiration_info_dom": record.expiration_info_dom or "",
        "storage_method_dom": record.storage_method_dom or "",
        "storage_type_dom": record.storage_type_dom or "",
        "food_name_candidate": record.food_name_candidate or "",
        "weight_raw": record.weight_raw or "",
        "quantity_raw": record.quantity_raw or "",
        "sales_unit_raw": record.sales_unit_raw or "",
    }
    if not record.downloaded_images:
        return [ManifestRow(**base, image_path="", source_image_url="")]

    rows: list[ManifestRow] = []
    for image in record.downloaded_images:
        rows.append(
            ManifestRow(
                **base,
                image_path=image.local_path,
                source_image_url=image.source_url,
            )
        )
    return rows


def write_manifest_csv(rows: list[ManifestRow], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.model_dump(mode="json"))
    return output_path


def append_failure_csv(record: CrawlFailureRecord, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    should_write_header = not output_path.exists() or output_path.stat().st_size == 0
    with output_path.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FAILURE_COLUMNS)
        if should_write_header:
            writer.writeheader()
        writer.writerow(record.model_dump(mode="json"))
