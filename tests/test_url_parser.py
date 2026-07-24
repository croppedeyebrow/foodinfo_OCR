from __future__ import annotations

from conftest import use_app

use_app("crawler")

from src.url_parser import (  # noqa: E402
    InvalidProductUrlError,
    canonicalize_kurly_url,
    load_unique_urls,
    parse_kurly_product_id,
)
import pytest


def test_parse_kurly_product_id() -> None:
    url = "https://www.kurly.com/goods/5047857?collectionCode=2607-vacanceonestop-home"
    assert parse_kurly_product_id(url) == "5047857"


def test_parse_naver_kurlynmart_product_id() -> None:
    url = (
        "https://shopping.naver.com/window-products/kurlynmart/12274518551"
        "?site_preference=device&NaPm=ct%3Dmrz0ifo3"
    )
    assert parse_kurly_product_id(url) == "12274518551"
    assert (
        canonicalize_kurly_url(url)
        == "https://shopping.naver.com/window-products/kurlynmart/12274518551"
    )


def test_canonicalize_kurly_url() -> None:
    url = "https://www.kurly.com/goods/5047857?collectionCode=2607-vacanceonestop-home"
    assert canonicalize_kurly_url(url) == "https://www.kurly.com/goods/5047857"


def test_parse_kurly_product_id_invalid() -> None:
    with pytest.raises(InvalidProductUrlError):
        parse_kurly_product_id("https://www.kurly.com/categories/001")


def test_reject_non_kurly_product_url() -> None:
    with pytest.raises(InvalidProductUrlError):
        canonicalize_kurly_url("https://example.com/goods/5047857")


def test_load_unique_urls_dedupes_by_product_id() -> None:
    lines = [
        "# comment",
        "",
        "https://www.kurly.com/goods/5047857?x=1",
        "https://www.kurly.com/goods/5047857?x=2",
        "https://www.kurly.com/goods/1111111",
        "https://shopping.naver.com/window-products/kurlynmart/12274518551?x=1",
        "https://shopping.naver.com/window-products/kurlynmart/12274518551?x=2",
    ]
    assert load_unique_urls(lines) == [
        "https://www.kurly.com/goods/5047857?x=1",
        "https://www.kurly.com/goods/1111111",
        "https://shopping.naver.com/window-products/kurlynmart/12274518551?x=1",
    ]
