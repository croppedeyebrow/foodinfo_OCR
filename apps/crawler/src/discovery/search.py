from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from ..config import CrawlerSettings
from ..models import DiscoveryFailure, DiscoveryMode
from ..url_parser import build_search_url
from .base import (
    DiscoveryError,
    DiscoveryResult,
    build_running_manifest,
    ensure_fresh_batch_dir,
    finalize_manifest,
)
from .page_scroller import discover_with_scroll


KST = ZoneInfo("Asia/Seoul")


class SearchProductDiscovery:
    def __init__(self, discovery_root: Path, settings: CrawlerSettings) -> None:
        self.discovery_root = discovery_root
        self.settings = settings

    def discover(
        self,
        page: Page,
        *,
        keyword: str,
        batch_id: str,
        max_products: int,
        max_scrolls: int,
    ) -> tuple[Path, DiscoveryResult]:
        cleaned = keyword.strip()
        if not cleaned:
            raise DiscoveryError("EMPTY_SEARCH_KEYWORD", "Search keyword is empty")

        batch_dir = ensure_fresh_batch_dir(self.discovery_root, batch_id)
        search_url = build_search_url(cleaned)
        manifest = build_running_manifest(
            batch_id=batch_id,
            source_mode=DiscoveryMode.SEARCH,
            source_value=cleaned,
            requested_url=search_url,
            max_products=max_products,
            max_scrolls=max_scrolls,
        )
        failures: list[DiscoveryFailure] = []

        try:
            timeout_ms = int(self.settings.crawler_timeout_seconds * 1000)
            page.set_extra_http_headers({"User-Agent": self.settings.crawler_user_agent})
            page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(800)
            outcome = discover_with_scroll(
                page,
                batch_id=batch_id,
                source_mode=DiscoveryMode.SEARCH,
                source_value=cleaned,
                max_products=max_products,
                max_scrolls=max_scrolls,
                scroll_wait_ms=self.settings.discovery_scroll_wait_ms,
                unchanged_limit=self.settings.discovery_unchanged_limit,
            )
        except PlaywrightTimeoutError as error:
            failures.append(
                DiscoveryFailure(
                    batch_id=batch_id,
                    source_mode=DiscoveryMode.SEARCH,
                    source_value=cleaned,
                    requested_url=search_url,
                    error_code="DISCOVERY_PAGE_TIMEOUT",
                    error_message=str(error),
                    failed_at=datetime.now(KST),
                )
            )
            manifest = finalize_manifest(
                manifest,
                products=[],
                duplicate_count=0,
                stop_reason=None,
                status="FAILED",
            )
            return batch_dir, DiscoveryResult(failures=failures, manifest=manifest)
        except Exception as error:  # noqa: BLE001
            failures.append(
                DiscoveryFailure(
                    batch_id=batch_id,
                    source_mode=DiscoveryMode.SEARCH,
                    source_value=cleaned,
                    requested_url=search_url,
                    error_code="DISCOVERY_PAGE_FETCH_FAILED",
                    error_message=str(error),
                    failed_at=datetime.now(KST),
                )
            )
            manifest = finalize_manifest(
                manifest,
                products=[],
                duplicate_count=0,
                stop_reason=None,
                status="FAILED",
            )
            return batch_dir, DiscoveryResult(failures=failures, manifest=manifest)

        products = outcome.products
        if not products:
            failures.append(
                DiscoveryFailure(
                    batch_id=batch_id,
                    source_mode=DiscoveryMode.SEARCH,
                    source_value=cleaned,
                    requested_url=search_url,
                    error_code="PRODUCT_LINK_NOT_FOUND",
                    error_message="No product links found on search page",
                    failed_at=datetime.now(KST),
                )
            )
            status = "FAILED"
        else:
            status = "COMPLETED"

        manifest = finalize_manifest(
            manifest,
            products=products,
            duplicate_count=outcome.duplicate_hits,
            stop_reason=outcome.stop_reason,
            status=status,
        )
        return batch_dir, DiscoveryResult(
            products=products,
            failures=failures,
            manifest=manifest,
            duplicate_count=outcome.duplicate_hits,
            stop_reason=outcome.stop_reason,
        )
