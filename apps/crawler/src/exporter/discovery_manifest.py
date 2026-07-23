from __future__ import annotations

import json
from pathlib import Path

from ..models import DiscoveryManifest


def write_discovery_manifest(manifest: DiscoveryManifest, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(output_path)
    return output_path
