from __future__ import annotations

from urllib.parse import urljoin, urlparse

from .models import ImageCandidate


EXCLUDE_KEYWORDS = (
    "review",
    "banner",
    "icon",
    "logo",
    "thumb",
    "recommend",
    "related",
    "sns",
    "share",
    "badge",
    "cart",
    "coupon",
    "recent-product",
    "상품-대표",
    "대표-이미지",
    "/brand/",
    "member",
    "profile",
)

DETAIL_HINTS = (
    "goodsview",
    "goods_wrap",
    "goods_intro",
    "goods_point",
    "goods_note",
    "goods-detail",
    "product-detail",
    "detail",
    "description",
    "notice",
    "disclosure",
    "고시",
    "상세",
    "goodsview",
)


def select_detail_image_candidates(
    images: list[dict[str, str | int | None]],
    base_url: str,
) -> list[ImageCandidate]:
    """상세설명·고시 영역 후보 이미지를 수집하고 대표/배너류는 제외한다."""
    seen_urls: set[str] = set()
    preferred: list[ImageCandidate] = []
    fallback: list[ImageCandidate] = []

    for image in images:
        raw_url = str(image.get("src") or image.get("data-src") or "").strip()
        if not raw_url or raw_url.startswith("data:"):
            continue
        absolute = urljoin(base_url, raw_url)
        normalized = _normalize_url(absolute)
        if not normalized or normalized in seen_urls:
            continue
        if _should_exclude(image, normalized):
            continue

        seen_urls.add(normalized)
        candidate = ImageCandidate(
            source_url=normalized,
            alt=_as_optional_str(image.get("alt")),
            width=_as_optional_int(image.get("width")),
            height=_as_optional_int(image.get("height")),
            dom_path=_as_optional_str(image.get("dom_path")),
        )
        if _is_preferred_detail(image, normalized):
            preferred.append(candidate)
        else:
            fallback.append(candidate)

    # 상세 영역 이미지가 있으면 그것만 사용한다.
    return preferred or fallback[:5]


def _is_preferred_detail(image: dict[str, str | int | None], url: str) -> bool:
    haystack = " ".join(
        str(value).lower()
        for value in (url, image.get("alt"), image.get("class_name"), image.get("dom_path"))
        if value
    )
    if any(hint in haystack for hint in DETAIL_HINTS):
        return True
    height = _as_optional_int(image.get("height"))
    width = _as_optional_int(image.get("width"))
    # 세로로 긴 상세/고시 이미지
    if height is not None and width is not None and height >= 900 and width >= 700:
        return True
    return False


def _should_exclude(image: dict[str, str | int | None], url: str) -> bool:
    haystack = " ".join(
        str(value).lower()
        for value in (
            url,
            image.get("alt"),
            image.get("class_name"),
            image.get("dom_path"),
        )
        if value
    )
    if any(keyword in haystack for keyword in EXCLUDE_KEYWORDS):
        return True

    width = _as_optional_int(image.get("width"))
    height = _as_optional_int(image.get("height"))
    if width is not None and height is not None:
        if width < 200 and height < 200:
            return True
        if width > 800 and height < 120:
            return True
        # 작은 썸네일
        if width <= 160 and height <= 200:
            return True

    if any(token in haystack for token in ("main", "hero", "cover", "recent")):
        if not any(hint in haystack for hint in DETAIL_HINTS):
            return True
    return False


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return parsed._replace(fragment="").geturl()


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None
