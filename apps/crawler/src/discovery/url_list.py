from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..models import DiscoveredProduct, DiscoveryFailure, DiscoveryMode
from ..url_parser import (
    InvalidProductUrlError,
    canonicalize_kurly_url,
    load_unique_urls,
    parse_kurly_product_id,
)
from .base import (
    DiscoveryResult,
    build_running_manifest,
    ensure_fresh_batch_dir,
    finalize_manifest,
)


KST = ZoneInfo("Asia/Seoul")


class UrlListProductDiscovery:
    def __init__(self, discovery_root: Path) -> None:
        self.discovery_root = discovery_root

    def discover(
        self,
        *,
        input_file: Path,
        batch_id: str,
    ) -> tuple[Path, DiscoveryResult]:
        batch_dir = ensure_fresh_batch_dir(self.discovery_root, batch_id)
        source_value = input_file.name
        requested_url = str(input_file)
        manifest = build_running_manifest(
            batch_id=batch_id,
            source_mode=DiscoveryMode.URL_LIST,
            source_value=source_value,
            requested_url=requested_url,
            max_products=None,
            max_scrolls=None,
        )

        lines = input_file.read_text(encoding="utf-8").splitlines()
        urls = load_unique_urls(lines)
        products: list[DiscoveredProduct] = []
        failures: list[DiscoveryFailure] = []
        duplicate_count = max(0, len([u for u in lines if u.strip() and not u.strip().startswith("#")]) - len(urls))

        for index, url in enumerate(urls, start=1):
            try:
                product_id = parse_kurly_product_id(url)
                canonical = canonicalize_kurly_url(url)
            except InvalidProductUrlError as error:
                failures.append(
                    DiscoveryFailure(
                        batch_id=batch_id,
                        source_mode=DiscoveryMode.URL_LIST,
                        source_value=source_value,
                        requested_url=url,
                        error_code=getattr(error, "error_code", "INVALID_PRODUCT_URL"),
                        error_message=str(error),
                        failed_at=datetime.now(KST),
                    )
                )
                continue
            products.append(
                DiscoveredProduct(
                    batch_id=batch_id,
                    source_mode=DiscoveryMode.URL_LIST,
                    source_value=source_value,
                    original_product_id=product_id,
                    product_name_preview=None,
                    product_url=canonical,  # type: ignore[arg-type]
                    discovery_order=len(products) + 1,
                    discovered_at=datetime.now(KST),
                )
            )

        status = "COMPLETED" if not failures else ("PARTIAL_FAILED" if products else "FAILED")
        if not products and not failures:
            status = "FAILED"
            failures.append(
                DiscoveryFailure(
                    batch_id=batch_id,
                    source_mode=DiscoveryMode.URL_LIST,
                    source_value=source_value,
                    requested_url=requested_url,
                    error_code="PRODUCT_LINK_NOT_FOUND",
                    error_message="No product URLs found in input file",
                    failed_at=datetime.now(KST),
                )
            )

        manifest = finalize_manifest(
            manifest,
            products=products,
            duplicate_count=duplicate_count,
            stop_reason=None,
            status=status,
        )
        result = DiscoveryResult(
            products=products,
            failures=failures,
            manifest=manifest,
            duplicate_count=duplicate_count,
        )
        return batch_dir, result
