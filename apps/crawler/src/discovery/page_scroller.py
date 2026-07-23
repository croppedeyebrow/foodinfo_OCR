from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..models import DiscoveredProduct, DiscoveryMode
from ..url_parser import canonicalize_product_url
from .link_extractor import extract_product_links_from_page, merge_link_candidates

if TYPE_CHECKING:
    from playwright.sync_api import Page


@dataclass
class ScrollDiscoveryOutcome:
    products: list[DiscoveredProduct]
    duplicate_hits: int
    stop_reason: str
    scroll_rounds: int


def discover_with_scroll(
    page: Any,
    *,
    batch_id: str,
    source_mode: DiscoveryMode,
    source_value: str,
    max_products: int,
    max_scrolls: int,
    scroll_wait_ms: int = 1500,
    unchanged_limit: int = 3,
) -> ScrollDiscoveryOutcome:
    known: dict[str, DiscoveredProduct] = {}
    duplicate_hits = 0
    unchanged_rounds = 0
    stop_reason = "SCROLL_LIMIT_REACHED"
    scroll_rounds = 0

    for scroll_index in range(max_scrolls):
        scroll_rounds = scroll_index + 1
        before_count = len(known)
        candidates = extract_product_links_from_page(page)
        for candidate in candidates:
            parsed = canonicalize_product_url(candidate.get("href", ""))
            if parsed and parsed[0] in known:
                duplicate_hits += 1

        merge_link_candidates(
            known,
            candidates,
            batch_id=batch_id,
            source_mode=source_mode,
            source_value=source_value,
        )

        if len(known) >= max_products:
            stop_reason = "MAX_PRODUCTS_REACHED"
            break

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(scroll_wait_ms)

        after_candidates = extract_product_links_from_page(page)
        for candidate in after_candidates:
            parsed = canonicalize_product_url(candidate.get("href", ""))
            if parsed and parsed[0] in known:
                duplicate_hits += 1

        merge_link_candidates(
            known,
            after_candidates,
            batch_id=batch_id,
            source_mode=source_mode,
            source_value=source_value,
        )

        if len(known) == before_count:
            unchanged_rounds += 1
        else:
            unchanged_rounds = 0

        if len(known) >= max_products:
            stop_reason = "MAX_PRODUCTS_REACHED"
            break
        if unchanged_rounds >= unchanged_limit:
            stop_reason = "NO_NEW_PRODUCTS"
            break
    else:
        stop_reason = "SCROLL_LIMIT_REACHED"

    ordered = sorted(known.values(), key=lambda item: item.discovery_order)[:max_products]
    for index, product in enumerate(ordered, start=1):
        product.discovery_order = index

    return ScrollDiscoveryOutcome(
        products=ordered,
        duplicate_hits=duplicate_hits,
        stop_reason=stop_reason,
        scroll_rounds=scroll_rounds,
    )


def simulate_scroll_discovery(
    rounds: list[list[dict[str, str]]],
    *,
    batch_id: str,
    source_mode: DiscoveryMode,
    source_value: str,
    max_products: int,
    max_scrolls: int,
    unchanged_limit: int = 3,
) -> ScrollDiscoveryOutcome:
    """네트워크 없이 스크롤 종료 조건을 단위 테스트한다."""
    known: dict[str, DiscoveredProduct] = {}
    duplicate_hits = 0
    unchanged_rounds = 0
    stop_reason = "SCROLL_LIMIT_REACHED"
    scroll_rounds = 0

    for scroll_index in range(min(max_scrolls, len(rounds))):
        scroll_rounds = scroll_index + 1
        before_count = len(known)
        candidates = rounds[scroll_index]
        for candidate in candidates:
            parsed = canonicalize_product_url(candidate.get("href", ""))
            if parsed and parsed[0] in known:
                duplicate_hits += 1
        merge_link_candidates(
            known,
            candidates,
            batch_id=batch_id,
            source_mode=source_mode,
            source_value=source_value,
        )
        if len(known) >= max_products:
            stop_reason = "MAX_PRODUCTS_REACHED"
            break
        if len(known) == before_count:
            unchanged_rounds += 1
        else:
            unchanged_rounds = 0
        if unchanged_rounds >= unchanged_limit:
            stop_reason = "NO_NEW_PRODUCTS"
            break
    else:
        if scroll_rounds >= max_scrolls and stop_reason != "MAX_PRODUCTS_REACHED":
            stop_reason = "SCROLL_LIMIT_REACHED"

    ordered = sorted(known.values(), key=lambda item: item.discovery_order)[:max_products]
    for index, product in enumerate(ordered, start=1):
        product.discovery_order = index
    return ScrollDiscoveryOutcome(
        products=ordered,
        duplicate_hits=duplicate_hits,
        stop_reason=stop_reason,
        scroll_rounds=scroll_rounds,
    )
