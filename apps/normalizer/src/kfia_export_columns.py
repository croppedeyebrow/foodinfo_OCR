from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import polars as pl

EXPORT_FILENAME = "shelf_life_output.csv"
NATIVE_CONTRACT_VERSION = "kfia_native_export_v1.0.0"

NATIVE_REQUIRED_COLUMNS = (
    "품목코드",
    "식품유형",
    "소비기한참고값_일",
    "단위",
    "온도별_상세_json",
    "source_pdf",
    "source_page",
    "추출일시",
)

NATIVE_OPTIONAL_COLUMNS = (
    "성상",
    "포장방법",
    "기존유통기한",
    "보존유통온도",
    "보관방법",
    "기준온도",
    "품질안전한계기간_일",
    "안전계수",
)

NATIVE_ALL_COLUMNS = NATIVE_REQUIRED_COLUMNS + NATIVE_OPTIONAL_COLUMNS

DATASET_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def normalize_header(name: str) -> str:
    return str(name).strip().lstrip("\ufeff")


def _read_csv_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    return raw.decode("utf-8")


def read_native_export(path: Path | str) -> pl.DataFrame:
    csv_text = _read_csv_text(Path(path))
    frame = pl.read_csv(
        csv_text.encode("utf-8"),
        infer_schema_length=2000,
        ignore_errors=True,
    )
    rename_map = {
        column: normalize_header(column)
        for column in frame.columns
        if normalize_header(column) != column
    }
    if rename_map:
        frame = frame.rename(rename_map)
    return frame


def missing_native_columns(frame: pl.DataFrame) -> list[str]:
    present = {normalize_header(column) for column in frame.columns}
    return [column for column in NATIVE_ALL_COLUMNS if column not in present]


def missing_required_native_columns(frame: pl.DataFrame) -> list[str]:
    present = {normalize_header(column) for column in frame.columns}
    return [column for column in NATIVE_REQUIRED_COLUMNS if column not in present]


def summarize_native_export(frame: pl.DataFrame) -> dict[str, Any]:
    rows = frame.to_dicts()
    json_valid = 0
    for row in rows:
        value = row.get("온도별_상세_json")
        if value in {None, ""}:
            continue
        try:
            import json

            parsed = json.loads(str(value))
            if isinstance(parsed, list):
                json_valid += 1
        except json.JSONDecodeError:
            continue

    def _present_ratio(column: str) -> str:
        filled = sum(1 for row in rows if str(row.get(column) or "").strip())
        return "있음" if filled == len(rows) and rows else f"{filled}/{len(rows)}"

    missing_required = missing_required_native_columns(frame)
    verdict = (
        "Native 계약 통과 / Bronze 등록 가능"
        if not missing_required
        else "Native 계약 실패"
    )
    return {
        "schema_version": "1.0.0",
        "row_count": frame.height,
        "columns": [normalize_header(column) for column in frame.columns],
        "required_columns_present": not missing_required,
        "missing_columns": missing_required,
        "checks": {
            "품목코드": _present_ratio("품목코드"),
            "식품유형": _present_ratio("식품유형"),
            "소비기한 참고값": _present_ratio("소비기한참고값_일"),
            "source_pdf": _present_ratio("source_pdf"),
            "source_page": _present_ratio("source_page"),
            "온도별 상세 JSON": f"{json_valid}/{frame.height} 유효",
            "raw_text": "미제공 · 선택 필드",
        },
        "verdict": verdict,
    }
