from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from ..submission import file_sha256

KST = ZoneInfo("Asia/Seoul")


def now_iso() -> str:
    return datetime.now(KST).isoformat()


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text)


def atomic_write_parquet(path: Path, frame: pl.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    frame.write_parquet(temporary)
    temporary.replace(path)


def atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def staging_dir(batch_dir: Path, attempt: int) -> Path:
    return batch_dir / f".staging-{attempt}"


def promote_staging(staging: Path, batch_dir: Path, filenames: tuple[str, ...]) -> None:
    batch_dir.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        source = staging / name
        if not source.is_file():
            continue
        target = batch_dir / name
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        source.replace(temporary)
        temporary.replace(target)
    if staging.is_dir():
        for child in staging.iterdir():
            if child.is_file():
                child.unlink(missing_ok=True)
        staging.rmdir()


def parquet_checksum(path: Path) -> str:
    return file_sha256(path)
