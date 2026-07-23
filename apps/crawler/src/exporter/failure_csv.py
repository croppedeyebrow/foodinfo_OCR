from __future__ import annotations

import csv
from pathlib import Path

from ..models import DiscoveryFailure


FAILURE_COLUMNS = list(DiscoveryFailure.model_fields)


def append_discovery_failure_csv(record: DiscoveryFailure, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    should_write_header = not output_path.exists() or output_path.stat().st_size == 0
    with output_path.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FAILURE_COLUMNS)
        if should_write_header:
            writer.writeheader()
        writer.writerow(record.model_dump(mode="json"))
