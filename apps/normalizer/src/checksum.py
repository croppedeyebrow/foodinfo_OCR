"""Canonical checksum for versioned contract payloads.

See ``dev_docs/data_platform/checksum_rules.md``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any


CONTENT_HASH_KEY = "content_hash"


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize(value[key])
            for key in sorted(value.keys(), key=lambda item: str(item))
            if key != CONTENT_HASH_KEY
        }
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return value.hex()
    return value


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize payload for hashing: sorted keys, UTF-8, compact separators."""
    normalized = _normalize(payload)
    text = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return text.encode("utf-8")


def compute_content_hash(payload: dict[str, Any]) -> str:
    """Return lowercase SHA-256 hex digest of the canonical JSON bytes."""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def with_content_hash(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow-copied payload with ``content_hash`` filled."""
    body = dict(payload)
    body.pop(CONTENT_HASH_KEY, None)
    digest = compute_content_hash(body)
    body[CONTENT_HASH_KEY] = digest
    return body
