from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

import pytest

from conftest import use_app

use_app("crawler")

from src.discovery.base import DiscoveryError, ensure_fresh_batch_dir  # noqa: E402
from src.discovery.link_extractor import (  # noqa: E402
    extract_product_links_from_html,
    merge_link_candidates,
)
from src.discovery.page_scroller import simulate_scroll_discovery  # noqa: E402
from src.exporter.discovery_csv import write_discovery_csv  # noqa: E402
from src.models import DiscoveryMode  # noqa: E402
from src.url_parser import (  # noqa: E402
    InvalidProductUrlError,
    build_category_url,
    build_search_url,
    canonicalize_kurly_url,
    canonicalize_product_url,
    parse_kurly_product_id,
    validate_category_inputs,
)


def test_extract_product_id_from_absolute_url() -> None:
    assert (
        parse_kurly_product_id(
            "https://www.kurly.com/goods/5047857?collectionCode=2607"
        )
        == "5047857"
    )


def test_extract_product_id_from_relative_url() -> None:
    assert canonicalize_product_url("/goods/5047857") == (
        "5047857",
        "https://www.kurly.com/goods/5047857",
    )


def test_remove_query_string_from_product_url() -> None:
    assert (
        canonicalize_kurly_url(
            "https://www.kurly.com/goods/5047857?collectionCode=2607-vacanceonestop-home"
        )
        == "https://www.kurly.com/goods/5047857"
    )


def test_reject_non_kurly_product_url() -> None:
    with pytest.raises(InvalidProductUrlError):
        canonicalize_kurly_url("https://example.com/goods/5047857")


def test_encode_korean_search_keyword() -> None:
    url = build_search_url("육류")
    assert url.startswith("https://www.kurly.com/search?sword=")
    assert "육류" == unquote(url.split("sword=", 1)[1])


def test_build_category_url() -> None:
    assert build_category_url("910") == "https://www.kurly.com/categories/910"


def test_validate_category_code_or_url_exclusive() -> None:
    with pytest.raises(ValueError):
        validate_category_inputs("910", "https://www.kurly.com/categories/910")
    with pytest.raises(ValueError):
        validate_category_inputs(None, None)
    code, url = validate_category_inputs("910", None)
    assert code == "910"
    assert url == "https://www.kurly.com/categories/910"


def test_deduplicate_products_by_id() -> None:
    known: dict = {}
    added = merge_link_candidates(
        known,
        [
            {"href": "/goods/1", "text": "A"},
            {"href": "/goods/1?x=1", "text": "A2"},
            {"href": "/goods/2", "text": "B"},
        ],
        batch_id="b1",
        source_mode=DiscoveryMode.SEARCH,
        source_value="육류",
    )
    assert added == 2
    assert set(known) == {"1", "2"}


def test_preserve_discovery_order() -> None:
    known: dict = {}
    merge_link_candidates(
        known,
        [
            {"href": "/goods/10", "text": "first"},
            {"href": "/goods/20", "text": "second"},
            {"href": "/goods/30", "text": "third"},
        ],
        batch_id="b1",
        source_mode=DiscoveryMode.CATEGORY,
        source_value="910",
    )
    ordered = sorted(known.values(), key=lambda item: item.discovery_order)
    assert [item.original_product_id for item in ordered] == ["10", "20", "30"]


def test_stop_when_max_products_reached() -> None:
    rounds = [
        [{"href": "/goods/1", "text": "a"}, {"href": "/goods/2", "text": "b"}],
        [{"href": "/goods/3", "text": "c"}, {"href": "/goods/4", "text": "d"}],
    ]
    outcome = simulate_scroll_discovery(
        rounds,
        batch_id="b1",
        source_mode=DiscoveryMode.SEARCH,
        source_value="육류",
        max_products=2,
        max_scrolls=10,
    )
    assert len(outcome.products) == 2
    assert outcome.stop_reason == "MAX_PRODUCTS_REACHED"


def test_stop_after_three_unchanged_scrolls() -> None:
    rounds = [
        [{"href": "/goods/1", "text": "a"}],
        [{"href": "/goods/1", "text": "a"}],
        [{"href": "/goods/1", "text": "a"}],
        [{"href": "/goods/1", "text": "a"}],
        [{"href": "/goods/9", "text": "new"}],
    ]
    outcome = simulate_scroll_discovery(
        rounds,
        batch_id="b1",
        source_mode=DiscoveryMode.SEARCH,
        source_value="육류",
        max_products=20,
        max_scrolls=10,
        unchanged_limit=3,
    )
    assert outcome.stop_reason == "NO_NEW_PRODUCTS"
    assert [p.original_product_id for p in outcome.products] == ["1"]


def test_write_discovery_csv_with_utf8_sig(tmp_path: Path) -> None:
    known: dict = {}
    merge_link_candidates(
        known,
        [{"href": "/goods/5047857", "text": "테스트"}],
        batch_id="20260723-jaeseong-001",
        source_mode=DiscoveryMode.URL_LIST,
        source_value="product_urls.txt",
    )
    output = tmp_path / "discovered_products.csv"
    write_discovery_csv(list(known.values()), output)
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")


def test_reject_existing_batch_directory(tmp_path: Path) -> None:
    batch_dir = tmp_path / "20260723-jaeseong-001"
    batch_dir.mkdir()
    with pytest.raises(DiscoveryError):
        ensure_fresh_batch_dir(tmp_path, "20260723-jaeseong-001")


def test_fixture_search_html_extracts_goods_links() -> None:
    html = (
        Path(__file__).parent / "fixtures" / "kurly_search_result.html"
    ).read_text(encoding="utf-8")
    links = extract_product_links_from_html(html)
    ids = []
    for item in links:
        parsed = canonicalize_product_url(item["href"])
        if parsed:
            ids.append(parsed[0])
    assert "5047857" in ids
    assert "1111111" in ids


def test_fixture_category_html_extracts_goods_links() -> None:
    html = (
        Path(__file__).parent / "fixtures" / "kurly_category_910.html"
    ).read_text(encoding="utf-8")
    links = extract_product_links_from_html(html)
    assert any("/goods/" in item["href"] for item in links)
