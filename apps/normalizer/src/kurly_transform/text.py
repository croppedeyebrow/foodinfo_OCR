from __future__ import annotations

import html
import re
from dataclasses import dataclass

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")

_STORAGE_ALIASES = {
    "REFRIGERATED": "REFRIGERATED",
    "FROZEN": "FROZEN",
    "ROOM": "ROOM",
    "UNKNOWN": "UNKNOWN",
    "냉장": "REFRIGERATED",
    "냉장보관": "REFRIGERATED",
    "냉장 보관": "REFRIGERATED",
    "냉동": "FROZEN",
    "냉동보관": "FROZEN",
    "냉동 보관": "FROZEN",
    "상온": "ROOM",
    "상온보관": "ROOM",
    "상온 보관": "ROOM",
    "실온": "ROOM",
}

_EXPIRATION_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"제조일.*?(\d+)\s*일"), "MANUFACTURE", "DAY"),
    (re.compile(r"제조일.*?(\d+)\s*개월"), "MANUFACTURE", "MONTH"),
    (re.compile(r"제조일.*?(\d+)\s*년"), "MANUFACTURE", "YEAR"),
    (re.compile(r"포장일.*?(\d+)\s*일"), "PACKING", "DAY"),
    (re.compile(r"포장일.*?(\d+)\s*개월"), "PACKING", "MONTH"),
    (re.compile(r"개봉.*?(\d+)\s*일"), "OPENING", "DAY"),
    (re.compile(r"구매일.*?(\d+)\s*일"), "UNKNOWN", "DAY"),
    (re.compile(r"(\d+)\s*일"), "UNKNOWN", "DAY"),
    (re.compile(r"(\d+)\s*개월"), "UNKNOWN", "MONTH"),
    (re.compile(r"(\d+)\s*년"), "UNKNOWN", "YEAR"),
    (re.compile(r"(\d+)\s*시간"), "UNKNOWN", "HOUR"),
)


@dataclass(frozen=True, slots=True)
class ExpirationParseResult:
    value: float | None
    unit: str | None
    basis: str | None
    review_required: bool


def clean_text(value: str | None) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = _HTML_TAG_RE.sub(" ", text)
    text = _CONTROL_CHAR_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def normalize_storage_type(
    *,
    storage_type_dom: str | None,
    storage_method_dom: str | None,
    storage_type_raw: str | None = None,
    storage_method_raw: str | None = None,
) -> tuple[str, bool]:
    candidates = [
        storage_type_dom,
        storage_type_raw,
        storage_method_dom,
        storage_method_raw,
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        normalized = clean_text(candidate).upper()
        if normalized in _STORAGE_ALIASES:
            return _STORAGE_ALIASES[normalized], False
        lowered = clean_text(candidate)
        if lowered in _STORAGE_ALIASES:
            return _STORAGE_ALIASES[lowered], False
    if any(candidates):
        return "UNKNOWN", True
    return "UNKNOWN", True


def parse_expiration(text: str | None) -> ExpirationParseResult:
    cleaned = clean_text(text)
    if not cleaned:
        return ExpirationParseResult(None, None, None, True)
    for pattern, basis, unit in _EXPIRATION_PATTERNS:
        match = pattern.search(cleaned)
        if match is None:
            continue
        value = float(match.group(1))
        review_required = basis == "UNKNOWN"
        return ExpirationParseResult(value, unit, basis, review_required)
    return ExpirationParseResult(None, None, None, True)


def is_dom_source(source: str | None) -> bool:
    return clean_text(source).upper() == "DOM"
