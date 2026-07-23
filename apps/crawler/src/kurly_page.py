from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from .config import CrawlerSettings
from .field_extractor import (
    build_food_name_candidate,
    extract_expiration_info,
    extract_labeled_text,
    extract_quantity,
    extract_sales_unit,
    extract_storage_method,
    extract_weight,
    normalize_storage_type,
)
from .image_candidate import select_detail_image_candidates
from .image_downloader import ImageDownloadError, download_images
from .models import CrawledProductRecord, KurlyProductUrl
from .url_parser import InvalidProductUrlError, parse_kurly_product_url


KST = ZoneInfo("Asia/Seoul")


class CrawlError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def collect_product(
    page: Page,
    requested_url: str,
    *,
    batch_id: str,
    data_root: Path,
    settings: CrawlerSettings,
) -> CrawledProductRecord:
    try:
        product_url = parse_kurly_product_url(requested_url)
    except InvalidProductUrlError as error:
        raise CrawlError("INVALID_PRODUCT_URL", str(error)) from error

    try:
        _open_product_page(page, product_url, settings)
    except PlaywrightTimeoutError as error:
        raise CrawlError("PAGE_TIMEOUT", str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise CrawlError("PAGE_FETCH_FAILED", str(error)) from error

    product_name = _extract_product_name(page)
    if not product_name:
        raise CrawlError("PRODUCT_NAME_NOT_FOUND", "Product name not found on page")

    _reveal_detail_section(page)
    page_text = _collect_page_text(page)
    image_payloads = _collect_image_payloads(page)
    candidates = select_detail_image_candidates(
        image_payloads,
        str(product_url.canonical_url),
    )

    sales_unit = extract_sales_unit(page_text) or _extract_from_definition_list(
        page, ("판매단위", "판매 단위")
    )
    weight = extract_weight(page_text, product_name) or _extract_from_definition_list(
        page, ("중량/용량", "중량", "용량")
    )
    quantity = extract_quantity(page_text) or _extract_from_definition_list(
        page, ("수량",)
    )
    expiration = extract_expiration_info(page_text) or _extract_from_definition_list(
        page, ("소비기한", "유통기한")
    )
    storage_method = extract_storage_method(page_text) or _extract_from_definition_list(
        page, ("보관방법", "보관 방법")
    )
    storage_type = normalize_storage_type(
        product_name,
        storage_method,
        extract_labeled_text(page_text, ("보관유형", "보관 유형")),
    )

    downloaded = []
    if candidates:
        try:
            downloaded = download_images(
                product_url.product_id,
                candidates,
                data_root / "detail_images",
                user_agent=settings.crawler_user_agent,
                timeout_seconds=settings.crawler_timeout_seconds,
                max_retries=settings.crawler_max_retries,
            )
        except ImageDownloadError as error:
            raise CrawlError(error.error_code, str(error)) from error

    if settings.crawler_save_html:
        html_dir = data_root / "html"
        html_dir.mkdir(parents=True, exist_ok=True)
        (html_dir / f"{product_url.product_id}.html").write_text(
            page.content(),
            encoding="utf-8",
        )

    return CrawledProductRecord(
        batch_id=batch_id,
        original_product_id=product_url.product_id,
        product_url=str(product_url.canonical_url),
        requested_url=str(product_url.requested_url),
        product_name_raw=product_name,
        food_name_candidate=build_food_name_candidate(product_name),
        sales_unit_raw=sales_unit,
        weight_raw=weight,
        quantity_raw=quantity,
        expiration_info_dom=expiration,
        storage_method_dom=storage_method,
        storage_type_dom=storage_type,
        detail_image_urls=[item.source_url for item in candidates],
        downloaded_images=downloaded,
        page_text=page_text,
        collected_at=datetime.now(KST),
        crawl_status="COMPLETED",
        image_candidates=candidates,
    )


def _open_product_page(
    page: Page,
    product_url: KurlyProductUrl,
    settings: CrawlerSettings,
) -> None:
    timeout_ms = int(settings.crawler_timeout_seconds * 1000)
    page.set_extra_http_headers({"User-Agent": settings.crawler_user_agent})
    page.goto(str(product_url.canonical_url), wait_until="domcontentloaded", timeout=timeout_ms)
    # 상품 핵심 정보 대기: h1 또는 상품명 후보
    selectors = ["h1", "[data-testid*='product']", "main h2", "main h1"]
    last_error: Exception | None = None
    for selector in selectors:
        try:
            page.wait_for_selector(selector, timeout=min(timeout_ms, 10000))
            return
        except Exception as error:  # noqa: BLE001
            last_error = error
    if last_error:
        raise last_error


def _extract_product_name(page: Page) -> str | None:
    candidates = [
        "h1",
        "[data-testid='product-name']",
        "[data-testid*='productName']",
        "main h1",
        "main h2",
    ]
    for selector in candidates:
        locator = page.locator(selector).first
        try:
            if locator.count() == 0:
                continue
            text = locator.inner_text(timeout=2000).strip()
            if text:
                return text
        except Exception:  # noqa: BLE001
            continue

    title = page.title()
    if title:
        # "상품명 | 컬리" 형태에서 앞부분만 사용
        return title.split("|")[0].strip() or None
    return None


def _reveal_detail_section(page: Page) -> None:
    detail_tab_labels = ("상품정보", "상세정보", "상품 설명", "상품고시정보")
    for label in detail_tab_labels:
        try:
            tab = page.get_by_role("tab", name=label)
            if tab.count() > 0:
                tab.first.click(timeout=2000)
                break
        except Exception:  # noqa: BLE001
            pass
        try:
            button = page.get_by_role("button", name=label)
            if button.count() > 0:
                button.first.click(timeout=2000)
                break
        except Exception:  # noqa: BLE001
            pass

    # 지연 로딩 이미지를 위해 단계적 스크롤
    for ratio in (0.25, 0.5, 0.75, 1.0):
        page.evaluate(
            """(ratio) => {
                const height = Math.max(
                    document.body.scrollHeight,
                    document.documentElement.scrollHeight
                );
                window.scrollTo(0, height * ratio);
            }""",
            ratio,
        )
        page.wait_for_timeout(400)


def _collect_page_text(page: Page) -> str:
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:  # noqa: BLE001
        return page.content()


def _collect_image_payloads(page: Page) -> list[dict[str, str | int | None]]:
    return page.evaluate(
        """() => {
            const images = Array.from(document.querySelectorAll("img"));
            return images.map((img) => {
                const rect = img.getBoundingClientRect();
                let node = img;
                const path = [];
                while (node && path.length < 6) {
                    const id = node.id ? `#${node.id}` : "";
                    const cls = (node.className && typeof node.className === "string")
                        ? "." + node.className.trim().split(/\\s+/).slice(0, 2).join(".")
                        : "";
                    path.push(`${node.tagName.toLowerCase()}${id}${cls}`);
                    node = node.parentElement;
                }
                return {
                    src: img.currentSrc || img.src || img.getAttribute("data-src") || "",
                    "data-src": img.getAttribute("data-src") || "",
                    alt: img.alt || "",
                    width: img.naturalWidth || Math.round(rect.width) || null,
                    height: img.naturalHeight || Math.round(rect.height) || null,
                    class_name: typeof img.className === "string" ? img.className : "",
                    dom_path: path.reverse().join(" > "),
                };
            });
        }"""
    )


def _extract_from_definition_list(page: Page, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        script = """(label) => {
            const nodes = Array.from(document.querySelectorAll("th, dt, strong, span, p, li"));
            for (const node of nodes) {
                const text = (node.textContent || "").replace(/\\s+/g, " ").trim();
                if (!text.includes(label)) continue;
                const next = node.nextElementSibling;
                if (next) {
                    const value = (next.textContent || "").replace(/\\s+/g, " ").trim();
                    if (value && value !== text) return value;
                }
                const parent = node.parentElement;
                if (parent) {
                    const parentText = (parent.textContent || "").replace(/\\s+/g, " ").trim();
                    const idx = parentText.indexOf(label);
                    if (idx >= 0) {
                        const rest = parentText.slice(idx + label.length).replace(/^[:：\\s]+/, "").trim();
                        if (rest) return rest;
                    }
                }
            }
            return null;
        }"""
        try:
            value = page.evaluate(script, label)
            if value:
                return str(value).strip()
        except Exception:  # noqa: BLE001
            continue
    return None


def sleep_between_requests(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)
