from __future__ import annotations

import re
from urllib.parse import quote, urlparse, urlunparse

from .models import KurlyProductUrl


PRODUCT_ID_PATTERN = re.compile(r"/goods/(?P<product_id>\d+)", re.IGNORECASE)
PRODUCT_PATH_PATTERN = PRODUCT_ID_PATTERN
CATEGORY_CODE_PATTERN = re.compile(r"^\d+$")
CATEGORY_PATH_PATTERN = re.compile(r"/categories/(?P<category_code>\d+)", re.IGNORECASE)


class InvalidProductUrlError(ValueError):
    error_code = "INVALID_PRODUCT_URL"


class InvalidCategoryError(ValueError):
    error_code = "INVALID_CATEGORY_URL"


def parse_kurly_product_id(url: str) -> str:
    match = PRODUCT_ID_PATTERN.search(url)
    if not match:
        raise InvalidProductUrlError(f"Cannot extract product id from URL: {url}")
    return match.group("product_id")


def canonicalize_kurly_url(url: str) -> str:
    product_id = parse_kurly_product_id(url)
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or "www.kurly.com"
    if netloc and "kurly.com" not in netloc.lower():
        raise InvalidProductUrlError(f"Non-Kurly product URL: {url}")
    return urlunparse((scheme, netloc, f"/goods/{product_id}", "", "", ""))


def canonicalize_product_url(href: str) -> tuple[str, str] | None:
    match = PRODUCT_PATH_PATTERN.search(href)
    if match is None:
        return None
    product_id = match.group("product_id")
    return product_id, f"https://www.kurly.com/goods/{product_id}"


def parse_kurly_product_url(url: str) -> KurlyProductUrl:
    product_id = parse_kurly_product_id(url)
    canonical = canonicalize_kurly_url(url)
    return KurlyProductUrl(
        requested_url=url,  # type: ignore[arg-type]
        product_id=product_id,
        canonical_url=canonical,  # type: ignore[arg-type]
    )


def build_search_url(keyword: str) -> str:
    cleaned = keyword.strip()
    if not cleaned:
        raise ValueError("EMPTY_SEARCH_KEYWORD")
    return f"https://www.kurly.com/search?sword={quote(cleaned)}"


def build_category_url(category_code: str) -> str:
    code = category_code.strip()
    if not CATEGORY_CODE_PATTERN.fullmatch(code):
        error = InvalidCategoryError(f"Invalid category code: {category_code}")
        error.error_code = "INVALID_CATEGORY_CODE"  # type: ignore[attr-defined]
        raise error
    return f"https://www.kurly.com/categories/{code}"


def parse_category_code_from_url(category_url: str) -> str:
    match = CATEGORY_PATH_PATTERN.search(category_url)
    if not match:
        error = InvalidCategoryError(f"Invalid category URL: {category_url}")
        error.error_code = "INVALID_CATEGORY_URL"  # type: ignore[attr-defined]
        raise error
    return match.group("category_code")


def validate_category_inputs(
    category_code: str | None,
    category_url: str | None,
) -> tuple[str, str]:
    """code와 url 중 하나만 허용하고 (code, absolute_url)을 반환한다."""
    has_code = bool(category_code and str(category_code).strip())
    has_url = bool(category_url and str(category_url).strip())
    if has_code == has_url:
        raise ValueError(
            "--category-code 또는 --category-url 중 하나만 입력해야 합니다."
        )
    if has_code:
        code = str(category_code).strip()
        return code, build_category_url(code)
    url = str(category_url).strip()
    code = parse_category_code_from_url(url)
    return code, build_category_url(code)


def load_unique_urls(lines: list[str]) -> list[str]:
    """빈 줄·주석을 제거하고 상품 ID 기준으로 중복을 제거한다."""
    seen_ids: set[str] = set()
    unique_urls: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            product_id = parse_kurly_product_id(line)
        except InvalidProductUrlError:
            unique_urls.append(line)
            continue
        if product_id in seen_ids:
            continue
        seen_ids.add(product_id)
        unique_urls.append(line)
    return unique_urls
