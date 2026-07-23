from __future__ import annotations

import re


STORAGE_TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("REFRIGERATED", ("냉장", "refrigerat")),
    ("FROZEN", ("냉동", "frozen")),
    ("ROOM_TEMPERATURE", ("상온", "실온", "room temperature")),
]

BRAND_PATTERN = re.compile(r"^\[[^\]]+\]\s*")
WEIGHT_IN_NAME_PATTERN = re.compile(
    r"\s*\d+(?:[.,]\d+)?\s*(?:kg|g|ml|l|L)\b", re.IGNORECASE
)
STORAGE_IN_NAME_PATTERN = re.compile(r"\s*\((?:냉장|냉동|상온|실온)\)\s*$")
ORIGIN_WORDS = ("호주산", "미국산", "국내산", "한우", "목초육", "곡물육")

PLACEHOLDER_VALUES = (
    "상품설명 및 상품이미지 참조",
    "상품 설명 및 상품이미지 참조",
)


def extract_labeled_text(page_text: str, labels: tuple[str, ...]) -> str | None:
    """레이블 다음 값을 본문 텍스트에서 추출한다.

    컬리 상세는 레이블과 값이 서로 다른 줄에 있는 경우가 많다.
    """
    if not page_text:
        return None

    lines = [re.sub(r"\s+", " ", line).strip() for line in page_text.splitlines()]
    lines = [line for line in lines if line]

    # 긴 레이블을 먼저 시도해 부분 문자열 오매칭을 줄인다.
    ordered_labels = sorted(labels, key=len, reverse=True)

    for index, line in enumerate(lines):
        compact = re.sub(r"\s+", "", line)
        for label in ordered_labels:
            compact_label = re.sub(r"\s+", "", label)
            if compact_label not in compact:
                continue

            # 같은 줄에서 레이블 앞뒤에 긴 본문이 있으면 오매칭으로 본다.
            if not _is_label_line(line, label):
                continue

            pattern = re.compile(
                re.escape(label).replace(r"\ ", r"\s*"),
                re.IGNORECASE,
            )
            remainder = pattern.sub("", line, count=1).strip()
            remainder = remainder.lstrip(" |:：・·").strip()

            if remainder and not _looks_like_label_residue(remainder):
                if not _is_placeholder(remainder):
                    return remainder

            if index + 1 < len(lines):
                nxt = lines[index + 1].strip()
                if nxt and not _is_placeholder(nxt) and not _looks_like_label_residue(nxt):
                    return nxt
    return None


def _is_label_line(line: str, label: str) -> bool:
    compact_line = re.sub(r"\s+", "", line)
    compact_label = re.sub(r"\s+", "", label)
    if compact_label not in compact_line:
        return False
    # 레이블이 줄 시작(또는 ・ 등 기호 뒤)에 있을 때만 허용
    idx = compact_line.find(compact_label)
    prefix = compact_line[:idx]
    return prefix in {"", "・", "-", "·"}


def _looks_like_label_residue(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    residues = (
        "정보",
        "또는유통기한",
        "또는취급방법",
        "또는품질유지기한",
        "(또는유통기한)정보",
        "또는취급방법",
    )
    if compact in residues:
        return True
    if compact.startswith("또는") and len(compact) <= 20:
        return True
    return False


def _is_placeholder(text: str) -> bool:
    return text.strip() in PLACEHOLDER_VALUES


def normalize_storage_type(*texts: str | None) -> str:
    combined = " ".join(text for text in texts if text).lower()
    if not combined:
        return "UNKNOWN"
    for storage_type, keywords in STORAGE_TYPE_RULES:
        if any(keyword.lower() in combined for keyword in keywords):
            return storage_type
    return "UNKNOWN"


def build_food_name_candidate(product_name: str | None) -> str | None:
    if not product_name:
        return None
    name = BRAND_PATTERN.sub("", product_name.strip())
    name = STORAGE_IN_NAME_PATTERN.sub("", name)
    name = WEIGHT_IN_NAME_PATTERN.sub("", name)
    for word in ORIGIN_WORDS:
        name = name.replace(word, " ")
    name = re.sub(r"\s+", " ", name).strip(" -/")
    return name or None


def extract_weight_from_name(product_name: str | None) -> str | None:
    if not product_name:
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?\s*(?:kg|g|ml|l|L))", product_name, re.IGNORECASE)
    return match.group(1).replace(" ", "") if match else None


def extract_sales_unit(page_text: str) -> str | None:
    return extract_labeled_text(page_text, ("판매단위", "판매 단위"))


def extract_weight(page_text: str, product_name: str | None = None) -> str | None:
    value = extract_labeled_text(page_text, ("중량/용량", "중량", "용량"))
    if value:
        return value
    # Kurly's Check Point: ・중량 : 1팩(250g / 2개입)
    match = re.search(
        r"중량\s*[:：]\s*([^\n]+)",
        page_text,
    )
    if match:
        chunk = match.group(1)
        weight = re.search(r"(\d+(?:[.,]\d+)?\s*(?:kg|g|ml|l|L))", chunk, re.IGNORECASE)
        if weight:
            return weight.group(1).replace(" ", "")
    return extract_weight_from_name(product_name)


def extract_quantity(page_text: str) -> str | None:
    # "구매 수량" UI 레이블은 제외하고 본문에서 개입 정보를 찾는다.
    match = re.search(r"(\d+\s*개입)", page_text)
    if match:
        return match.group(1).replace(" ", "")
    value = extract_labeled_text(page_text, ("팩 수량", "개수"))
    if value and value not in {"구매", "선택"}:
        return value
    return None


def extract_expiration_info(page_text: str) -> str | None:
    return extract_labeled_text(
        page_text,
        (
            "소비기한(또는 유통기한)정보",
            "소비기한 정보",
            "소비기한",
            "유통기한",
            "품질유지기한",
        ),
    )


def extract_storage_method(page_text: str) -> str | None:
    # Kurly's Check Point 우선
    match = re.search(r"보관법\s*[:：]\s*([^\n]+)", page_text)
    if match:
        value = match.group(1).strip()
        if value and not _is_placeholder(value):
            return value
    return extract_labeled_text(
        page_text,
        (
            "보관방법 또는 취급방법",
            "보관방법",
            "보관 방법",
            "보관안내",
            "보관법",
        ),
    )
