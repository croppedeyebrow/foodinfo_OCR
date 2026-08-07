"""Storage path helpers for Bronze / inbox / Silver / Gold / quarantine."""

from __future__ import annotations

from pathlib import Path


LAYER_DIRS = (
    "discovery",
    "crawl_raw",
    "detail_images",
    "ocr_raw",
    "inbox/accepted",
    "silver",
    "gold",
    "quarantine",
)


def ensure_storage_dirs(data_root: Path) -> list[Path]:
    created: list[Path] = []
    for relative in LAYER_DIRS:
        path = data_root / relative
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)
    return created


def discovery_batch_dir(data_root: Path, batch_id: str) -> Path:
    return data_root / "discovery" / batch_id


def accepted_inbox_dir(data_root: Path, batch_id: str) -> Path:
    return data_root / "inbox" / "accepted" / batch_id


def silver_batch_dir(data_root: Path, source: str, batch_id: str) -> Path:
    return data_root / "silver" / source / batch_id


def gold_dataset_dir(data_root: Path, dataset: str, version: str) -> Path:
    return data_root / "gold" / dataset / version


def quarantine_batch_dir(data_root: Path, batch_id: str) -> Path:
    return data_root / "quarantine" / batch_id


def batch_manifest_path(batch_dir: Path) -> Path:
    return batch_dir / "manifest.json"
