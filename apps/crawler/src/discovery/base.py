from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..models import DiscoveredProduct, DiscoveryFailure, DiscoveryManifest, DiscoveryMode


KST = ZoneInfo("Asia/Seoul")


class DiscoveryError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass
class DiscoveryResult:
    products: list[DiscoveredProduct] = field(default_factory=list)
    failures: list[DiscoveryFailure] = field(default_factory=list)
    manifest: DiscoveryManifest | None = None
    duplicate_count: int = 0
    stop_reason: str | None = None


def ensure_fresh_batch_dir(discovery_root: Path, batch_id: str) -> Path:
    batch_dir = discovery_root / batch_id
    if batch_dir.exists():
        raise DiscoveryError(
            "DISCOVERY_EXPORT_FAILED",
            f"Discovery batch directory already exists: {batch_dir}. Use a new batch-id.",
        )
    batch_dir.mkdir(parents=True, exist_ok=False)
    return batch_dir


def build_running_manifest(
    *,
    batch_id: str,
    source_mode: DiscoveryMode,
    source_value: str,
    requested_url: str,
    max_products: int | None,
    max_scrolls: int | None,
) -> DiscoveryManifest:
    return DiscoveryManifest(
        batch_id=batch_id,
        source_mode=source_mode,
        source_value=source_value,
        requested_url=requested_url,
        max_products=max_products,
        max_scrolls=max_scrolls,
        started_at=datetime.now(KST),
        status="RUNNING",
    )


def finalize_manifest(
    manifest: DiscoveryManifest,
    *,
    products: list[DiscoveredProduct],
    duplicate_count: int,
    stop_reason: str | None,
    status: str,
) -> DiscoveryManifest:
    manifest.discovered_count = len(products)
    manifest.duplicate_count = duplicate_count
    manifest.stop_reason = stop_reason
    manifest.finished_at = datetime.now(KST)
    manifest.status = status
    return manifest
