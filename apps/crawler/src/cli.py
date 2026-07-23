from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import typer
from playwright.sync_api import sync_playwright

from .config import load_settings
from .discovery import UrlListProductDiscovery
from .discovery.base import DiscoveryError
from .discovery.search import SearchProductDiscovery
from .discovery.category import CategoryProductDiscovery
from .exporter import (
    append_discovery_failure_csv,
    write_discovery_csv,
    write_discovery_manifest,
)
from .kurly_page import collect_product, sleep_between_requests
from .manifest_exporter import append_failure_csv, build_manifest_rows, write_manifest_csv
from .models import CrawlFailureRecord, ManifestRow
from .raw_exporter import write_raw_json
from .url_parser import (
    InvalidCategoryError,
    InvalidProductUrlError,
    load_unique_urls,
    parse_kurly_product_id,
    validate_category_inputs,
)

app = typer.Typer(no_args_is_help=True)
KST = ZoneInfo("Asia/Seoul")


def _persist_discovery(batch_dir: Path, result) -> None:
    assert result.manifest is not None
    write_discovery_csv(result.products, batch_dir / "discovered_products.csv")
    write_discovery_manifest(result.manifest, batch_dir / "manifest.json")
    for failure in result.failures:
        append_discovery_failure_csv(failure, batch_dir / "discovery_failures.csv")
    typer.echo(f"Discovery CSV: {batch_dir / 'discovered_products.csv'}")
    typer.echo(f"Manifest: {batch_dir / 'manifest.json'}")
    typer.echo(
        f"Discovered={len(result.products)}, duplicates={result.duplicate_count}, "
        f"status={result.manifest.status}, stop={result.stop_reason}"
    )


@app.command()
def health() -> None:
    """브라우저와 호스트 데이터 볼륨을 확인한다."""
    data_dir = Path("/data")
    for name in ("images", "html", "crawl_raw", "detail_images", "discovery"):
        (data_dir / name).mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        version = browser.version
        browser.close()

    typer.echo("Crawler container OK")
    typer.echo(f"Chromium version: {version}")
    typer.echo(f"Data directory: {data_dir}")


@app.command()
def collect(
    input_file: Path = typer.Option(
        Path("/data/input/product_urls.txt"), "--input", exists=True
    ),
) -> None:
    """상품 URL 목록을 읽는다. 상세 수집은 collect-batch/collect-details를 사용한다."""
    urls = load_unique_urls(input_file.read_text(encoding="utf-8").splitlines())
    typer.echo(f"Loaded product URLs: {len(urls)}")
    for url in urls:
        typer.echo(url)


@app.command("discover-urls")
def discover_urls(
    input_file: Path = typer.Option(..., "--input", exists=True),
    batch_id: str = typer.Option(..., "--batch-id"),
    data_root: Path = typer.Option(Path("/data"), "--data-root"),
) -> None:
    """URL 목록을 검증·정규화하여 discovered_products.csv를 생성한다."""
    discovery = UrlListProductDiscovery(data_root / "discovery")
    try:
        batch_dir, result = discovery.discover(input_file=input_file, batch_id=batch_id)
    except DiscoveryError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    _persist_discovery(batch_dir, result)
    if result.manifest and result.manifest.status == "FAILED":
        raise typer.Exit(code=1)


@app.command("discover-search")
def discover_search(
    keyword: str = typer.Option(..., "--keyword"),
    batch_id: str = typer.Option(..., "--batch-id"),
    max_products: int = typer.Option(20, "--max-products", min=1, max=500),
    max_scrolls: int = typer.Option(10, "--max-scrolls", min=1, max=100),
    data_root: Path = typer.Option(Path("/data"), "--data-root"),
) -> None:
    """컬리 검색 결과에서 상품 URL을 발견한다."""
    settings = load_settings()
    discovery = SearchProductDiscovery(data_root / "discovery", settings)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.crawler_headless)
        context = browser.new_context(user_agent=settings.crawler_user_agent)
        page = context.new_page()
        try:
            batch_dir, result = discovery.discover(
                page,
                keyword=keyword,
                batch_id=batch_id,
                max_products=max_products,
                max_scrolls=max_scrolls,
            )
        except DiscoveryError as error:
            typer.echo(str(error), err=True)
            context.close()
            browser.close()
            raise typer.Exit(code=1) from error
        context.close()
        browser.close()
    _persist_discovery(batch_dir, result)
    if result.manifest and result.manifest.status == "FAILED":
        raise typer.Exit(code=1)


@app.command("discover-category")
def discover_category(
    batch_id: str = typer.Option(..., "--batch-id"),
    category_code: str | None = typer.Option(None, "--category-code"),
    category_url: str | None = typer.Option(None, "--category-url"),
    max_products: int = typer.Option(20, "--max-products", min=1, max=500),
    max_scrolls: int = typer.Option(10, "--max-scrolls", min=1, max=100),
    data_root: Path = typer.Option(Path("/data"), "--data-root"),
) -> None:
    """컬리 카테고리에서 상품 URL을 발견한다."""
    try:
        validate_category_inputs(category_code, category_url)
    except (ValueError, InvalidCategoryError) as error:
        raise typer.BadParameter(str(error)) from error

    settings = load_settings()
    discovery = CategoryProductDiscovery(data_root / "discovery", settings)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.crawler_headless)
        context = browser.new_context(user_agent=settings.crawler_user_agent)
        page = context.new_page()
        try:
            batch_dir, result = discovery.discover(
                page,
                batch_id=batch_id,
                category_code=category_code,
                category_url=category_url,
                max_products=max_products,
                max_scrolls=max_scrolls,
            )
        except (ValueError, InvalidCategoryError, DiscoveryError) as error:
            typer.echo(str(error), err=True)
            context.close()
            browser.close()
            raise typer.Exit(code=1) from error
        context.close()
        browser.close()
    _persist_discovery(batch_dir, result)
    if result.manifest and result.manifest.status == "FAILED":
        raise typer.Exit(code=1)


@app.command("collect-details")
def collect_details(
    manifest: Path = typer.Option(..., "--manifest", exists=True),
    force: bool = typer.Option(False, "--force"),
    data_root: Path = typer.Option(Path("/data"), "--data-root"),
    output_manifest: Path = typer.Option(
        Path("/data/input/crawled_products.csv"), "--output-manifest"
    ),
) -> None:
    """discovered_products.csv를 읽어 상품 상세페이지를 수집한다."""
    settings = load_settings()
    outcome_root = Path(os.getenv("OUTCOME_ROOT", "/outcome"))
    member = os.getenv("BATCH_MEMBER", "unknown")

    rows: list[dict[str, str]] = []
    with manifest.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        typer.echo("No discovered products in manifest.", err=True)
        raise typer.Exit(code=1)

    crawl_raw_dir = data_root / "crawl_raw"
    manifest_rows: list[ManifestRow] = []
    success_count = 0
    skip_count = 0
    failure_count = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.crawler_headless)
        context = browser.new_context(user_agent=settings.crawler_user_agent)
        page = context.new_page()

        for index, row in enumerate(rows):
            batch_id = row.get("batch_id") or "UNKNOWN_BATCH"
            product_id = row.get("original_product_id") or ""
            product_url = row.get("product_url") or ""
            raw_path = crawl_raw_dir / f"{product_id}.json"
            if product_id and raw_path.exists() and not force:
                skip_count += 1
                typer.echo(f"SKIP: {product_id} (crawl_raw exists)")
                continue
            if index > 0:
                sleep_between_requests(settings.crawler_request_interval_seconds)
            try:
                record = collect_product(
                    page,
                    product_url,
                    batch_id=batch_id,
                    data_root=data_root,
                    settings=settings,
                )
                write_raw_json(record, crawl_raw_dir)
                manifest_rows.extend(build_manifest_rows(record))
                success_count += 1
                typer.echo(f"OK: {record.original_product_id}")
            except Exception as error:  # noqa: BLE001
                failure_count += 1
                failure = CrawlFailureRecord(
                    batch_id=batch_id,
                    source_site=row.get("source_site") or "KURLY",
                    original_product_id=product_id,
                    product_url=product_url,
                    requested_url=product_url,
                    error_code=getattr(error, "error_code", "PAGE_FETCH_FAILED"),
                    error_message=str(error),
                    failed_at=datetime.now(KST),
                )
                append_failure_csv(
                    failure,
                    outcome_root / member / batch_id / "failures.csv",
                )
                typer.echo(f"FAILED: {product_id or product_url}: {error}", err=True)

        context.close()
        browser.close()

    if manifest_rows:
        # force/부분 재수집 시 기존 crawled_products와 병합하지 않고 이번 성공분만 기록
        # (기존 파일에 append하려면 별도 옵션이 필요 — MVP는 덮어쓰기)
        if output_manifest.exists() and not force:
            # 기존 행 유지 + 신규 상품만 추가
            existing: list[dict[str, str]] = []
            with output_manifest.open("r", encoding="utf-8-sig", newline="") as file:
                existing = list(csv.DictReader(file))
            existing_ids = {
                (row.get("original_product_id"), row.get("image_path")) for row in existing
            }
            merged = list(existing)
            for item in manifest_rows:
                key = (item.original_product_id, item.image_path)
                if key not in existing_ids:
                    merged.append(item.model_dump(mode="json"))
                    existing_ids.add(key)
            from .manifest_exporter import MANIFEST_COLUMNS

            output_manifest.parent.mkdir(parents=True, exist_ok=True)
            with output_manifest.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=MANIFEST_COLUMNS)
                writer.writeheader()
                for row in merged:
                    if isinstance(row, ManifestRow):
                        writer.writerow(row.model_dump(mode="json"))
                    else:
                        writer.writerow({col: row.get(col, "") for col in MANIFEST_COLUMNS})
        else:
            write_manifest_csv(manifest_rows, output_manifest)

    typer.echo(f"Output manifest: {output_manifest}")
    typer.echo(
        f"Completed: success={success_count}, skipped={skip_count}, failure={failure_count}"
    )


@app.command("collect-batch")
def collect_batch(
    input_file: Path = typer.Option(
        Path("/data/input/product_urls.txt"), "--input", exists=True
    ),
    batch_id: str = typer.Option(..., "--batch-id"),
    data_root: Path = typer.Option(Path("/data"), "--data-root"),
    manifest_path: Path = typer.Option(
        Path("/data/input/crawled_products.csv"), "--manifest"
    ),
) -> None:
    """URL 목록을 순차 수집하고 crawl_raw/manifest를 생성한다. (기존 호환)"""
    settings = load_settings()
    urls = load_unique_urls(input_file.read_text(encoding="utf-8").splitlines())
    if not urls:
        typer.echo("No product URLs found.", err=True)
        raise typer.Exit(code=1)

    outcome_root = Path(os.getenv("OUTCOME_ROOT", "/outcome"))
    member = os.getenv("BATCH_MEMBER", "unknown")
    failure_path = outcome_root / member / batch_id / "failures.csv"

    manifest_rows: list[ManifestRow] = []
    success_count = 0
    failure_count = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.crawler_headless)
        context = browser.new_context(user_agent=settings.crawler_user_agent)
        page = context.new_page()

        for index, url in enumerate(urls):
            if index > 0:
                sleep_between_requests(settings.crawler_request_interval_seconds)
            try:
                record = collect_product(
                    page,
                    url,
                    batch_id=batch_id,
                    data_root=data_root,
                    settings=settings,
                )
                write_raw_json(record, data_root / "crawl_raw")
                manifest_rows.extend(build_manifest_rows(record))
                success_count += 1
                typer.echo(f"OK: {record.original_product_id}")
            except Exception as error:  # noqa: BLE001
                failure_count += 1
                product_id = ""
                try:
                    product_id = parse_kurly_product_id(url)
                except InvalidProductUrlError:
                    product_id = ""
                error_code = getattr(error, "error_code", "PAGE_FETCH_FAILED")
                failure = CrawlFailureRecord(
                    batch_id=batch_id,
                    original_product_id=product_id,
                    product_url=url,
                    requested_url=url,
                    error_code=error_code,
                    error_message=str(error),
                    failed_at=datetime.now(KST),
                )
                append_failure_csv(failure, failure_path)
                typer.echo(f"FAILED: {product_id or url}: {error}", err=True)

        context.close()
        browser.close()

    write_manifest_csv(manifest_rows, manifest_path)
    typer.echo(f"Manifest: {manifest_path}")
    typer.echo(f"Completed: success={success_count}, failure={failure_count}")


if __name__ == "__main__":
    app()
