from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ..models import DiscoveredProduct, DiscoveryMode
from ..url_parser import canonicalize_product_url


KST = ZoneInfo("Asia/Seoul")


def extract_product_links_from_page(page) -> list[dict[str, str]]:
    """Playwright page에서 /goods/ 링크 후보를 수집한다."""
    return page.evaluate(
        """() => {
            const anchors = Array.from(document.querySelectorAll("a[href*='/goods/']"));
            return anchors.map((anchor) => {
                const href = anchor.href || anchor.getAttribute("href") || "";
                let text = (anchor.innerText || anchor.textContent || "").replace(/\\s+/g, " ").trim();
                if (!text) {
                    const img = anchor.querySelector("img[alt]");
                    text = img ? (img.getAttribute("alt") || "").trim() : "";
                }
                if (!text) {
                    const card = anchor.closest("li, article, div");
                    const img = card ? card.querySelector("img[alt]") : null;
                    text = img ? (img.getAttribute("alt") || "").trim() : "";
                }
                return { href, text };
            });
        }"""
    )


def extract_product_links_from_html(html: str) -> list[dict[str, str]]:
    """단위 테스트용: HTML 문자열에서 /goods/ 링크를 추출한다."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, str]] = []
    for anchor in soup.select("a[href*='/goods/']"):
        href = anchor.get("href") or ""
        text = " ".join(anchor.stripped_strings)
        if not text:
            img = anchor.find("img", alt=True)
            text = (img.get("alt") if img else "") or ""
        if not text:
            parent = anchor.find_parent(["li", "article", "div"])
            img = parent.find("img", alt=True) if parent else None
            text = (img.get("alt") if img else "") or ""
        results.append({"href": href, "text": text.strip()})
    return results


def merge_link_candidates(
    known: dict[str, DiscoveredProduct],
    candidates: list[dict[str, str]],
    *,
    batch_id: str,
    source_mode: DiscoveryMode,
    source_value: str,
) -> int:
    """신규 상품만 known에 추가하고 추가 개수를 반환한다. discovery_order는 삽입 순서를 유지."""
    added = 0
    for candidate in candidates:
        parsed = canonicalize_product_url(candidate.get("href", ""))
        if parsed is None:
            continue
        product_id, canonical_url = parsed
        if product_id in known:
            continue
        preview = (candidate.get("text") or "").strip() or None
        order = len(known) + 1
        known[product_id] = DiscoveredProduct(
            batch_id=batch_id,
            source_mode=source_mode,
            source_value=source_value,
            original_product_id=product_id,
            product_name_preview=preview,
            product_url=canonical_url,  # type: ignore[arg-type]
            discovery_order=order,
            discovered_at=datetime.now(KST),
        )
        added += 1
    return added
