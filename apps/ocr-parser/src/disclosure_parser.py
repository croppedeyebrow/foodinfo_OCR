from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class DisclosureFields:
    food_type_raw: str | None
    expiration_info_raw: str | None
    storage_method_raw: str | None

    @property
    def has_any_value(self) -> bool:
        return any((self.food_type_raw, self.expiration_info_raw, self.storage_method_raw))


FIELD_ALIASES = {
    "food_type": ("식품의 유형", "식품유형", "제품의 유형"),
    "expiration": ("소비기한", "유통기한", "품질유지기한"),
    "storage": (
        "보관방법",
        "보관 및 취급방법",
        "보관 및 취급 시 주의사항",
        "보존 및 유통온도",
    ),
}


def parse_disclosure_text(text: str) -> DisclosureFields:
    normalized_lines = _normalize_lines(text)
    return DisclosureFields(
        food_type_raw=_extract_value(normalized_lines, FIELD_ALIASES["food_type"]),
        expiration_info_raw=_extract_value(normalized_lines, FIELD_ALIASES["expiration"]),
        storage_method_raw=_extract_value(normalized_lines, FIELD_ALIASES["storage"]),
    )


def _normalize_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.replace("\r", "\n").split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip(" |:：")
        if line:
            lines.append(line)
    return lines


def _extract_value(lines: list[str], aliases: tuple[str, ...]) -> str | None:
    for index, line in enumerate(lines):
        compact_line = re.sub(r"\s+", "", line)
        for alias in aliases:
            compact_alias = re.sub(r"\s+", "", alias)
            position = compact_line.find(compact_alias)
            if position < 0:
                continue

            pattern = re.compile(re.escape(alias).replace(r"\ ", r"\s*"), re.IGNORECASE)
            value = pattern.sub("", line, count=1).strip(" |:：")
            if value:
                return value
            if index + 1 < len(lines):
                return lines[index + 1]
    return None
