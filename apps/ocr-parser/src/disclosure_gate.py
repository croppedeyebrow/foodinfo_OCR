"""Low-resolution gate for deciding whether full-resolution OCR is needed."""

from __future__ import annotations

import os


DEFAULT_DISCLOSURE_GATE_MAX_IMAGE_SIDE = 640
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

# These are the same target fields the OCR pipeline already extracts.
TARGET_FIELD_KEYWORDS = (
    "소비기한",
    "유통기한",
    "보관방법",
    "보관",
    "식품유형",
    "식품의 유형",
)


def disclosure_gate_enabled() -> bool:
    """Return whether a low-resolution OCR gate runs before full OCR."""
    raw = os.getenv("OCR_DISCLOSURE_GATE_ENABLED", "true").strip().lower()
    return raw in TRUE_VALUES


def disclosure_gate_max_image_side() -> int:
    """Maximum longest side used by the low-resolution OCR gate."""
    raw = os.getenv(
        "OCR_DISCLOSURE_GATE_MAX_IMAGE_SIDE",
        str(DEFAULT_DISCLOSURE_GATE_MAX_IMAGE_SIDE),
    ).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_DISCLOSURE_GATE_MAX_IMAGE_SIDE
    return max(1, value)


def has_disclosure_keywords(text: str) -> bool:
    """Whether recognized text contains a field this pipeline extracts."""
    compact = text.replace(" ", "")
    return any(keyword.replace(" ", "") in compact for keyword in TARGET_FIELD_KEYWORDS)
