from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .config import get_settings
from .runner import (
    JobRunner,
    build_classify_images_command,
    build_collect_details_command,
    build_discover_category_command,
    build_discover_search_command,
    build_discover_urls_command,
    build_process_batch_command,
)
from .summaries import count_csv_rows, list_discovery_batches, summarize_text_checks

app = FastAPI(title="Kurly Pipeline Console")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
runner = JobRunner(project_root=str(get_settings().project_root))
KST = ZoneInfo("Asia/Seoul")


def _base_context(active_step: str) -> dict:
    settings = get_settings()
    return {
        "batch_member": settings.batch_member,
        "active_step": active_step,
        "status": runner.status(),
    }


def _suggested_batch_id() -> str:
    settings = get_settings()
    today = datetime.now(KST).strftime("%Y%m%d")
    return f"{today}-{settings.batch_member}-001"


def _batches(
    *,
    member_only: bool = True,
    require_file: str | None = None,
) -> list[str]:
    settings = get_settings()
    member = settings.batch_member if member_only else None
    if member in {None, "", "unknown", "member-name"}:
        member = None
    return list_discovery_batches(
        settings.discovery_root,
        member_filter=member,
        require_file=require_file,
    )


def _discover_summary(batch_id: str) -> dict | None:
    if not batch_id:
        return None
    settings = get_settings()
    path = settings.discovery_batch_dir(batch_id) / "discovered_products.csv"
    csv_summary = count_csv_rows(path)
    return {
        "kind": "csv",
        "exists": csv_summary.exists,
        "row_count": csv_summary.row_count,
        "path": str(path),
    }


def _collect_summary(batch_id: str) -> dict | None:
    if not batch_id:
        return None
    settings = get_settings()
    path = settings.discovery_batch_dir(batch_id) / "crawled_products.csv"
    csv_summary = count_csv_rows(path)
    return {
        "kind": "csv",
        "exists": csv_summary.exists,
        "row_count": csv_summary.row_count,
        "path": str(path),
    }


def _classify_summary(batch_id: str) -> dict | None:
    if not batch_id:
        return None
    settings = get_settings()
    path = settings.discovery_batch_dir(batch_id) / "image_text_check.csv"
    check = summarize_text_checks(path)
    return {
        "kind": "text_check",
        "exists": check.exists,
        "row_count": check.row_count,
        "has_text": check.has_text,
        "no_text": check.no_text,
        "unknown": check.unknown,
        "path": str(path),
    }


def _ocr_summary(batch_id: str) -> dict | None:
    if not batch_id:
        return None
    settings = get_settings()
    batch_dir = settings.outcome_batch_dir(batch_id)
    products = count_csv_rows(batch_dir / "products.csv")
    failures = count_csv_rows(batch_dir / "failures.csv")
    return {
        "kind": "ocr",
        "products_exists": products.exists,
        "products_rows": products.row_count,
        "products_path": str(products.path),
        "failures_exists": failures.exists,
        "failures_rows": failures.row_count,
        "failures_path": str(failures.path),
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "home.html",
        _base_context("home"),
    )


@app.get("/steps/discover", response_class=HTMLResponse)
def step_discover(request: Request, batch_id: str | None = None) -> HTMLResponse:
    selected = batch_id or ""
    context = _base_context("discover")
    context.update(
        {
            "suggested_batch_id": _suggested_batch_id(),
            "summary": _discover_summary(selected) if selected else None,
        }
    )
    return templates.TemplateResponse(request, "step_discover.html", context)


@app.get("/steps/collect", response_class=HTMLResponse)
def step_collect(request: Request, batch_id: str | None = None) -> HTMLResponse:
    batches = _batches(require_file="discovered_products.csv")
    selected = batch_id or (batches[0] if batches else "")
    context = _base_context("collect")
    context.update(
        {
            "batches": batches,
            "selected_batch": selected,
            "summary": _collect_summary(selected),
            "empty_batches_hint": "discovered_products.csv가 있는 배치가 없습니다. 1단계 발견을 먼저 실행하세요.",
        }
    )
    return templates.TemplateResponse(request, "step_collect.html", context)


@app.get("/steps/classify", response_class=HTMLResponse)
def step_classify(request: Request, batch_id: str | None = None) -> HTMLResponse:
    batches = _batches(require_file="crawled_products.csv")
    selected = batch_id or (batches[0] if batches else "")
    context = _base_context("classify")
    context.update(
        {
            "batches": batches,
            "selected_batch": selected,
            "summary": _classify_summary(selected),
            "empty_batches_hint": "crawled_products.csv가 있는 배치가 없습니다. 2단계 상세 수집을 먼저 실행하세요.",
        }
    )
    return templates.TemplateResponse(request, "step_classify.html", context)


@app.get("/steps/ocr", response_class=HTMLResponse)
def step_ocr(request: Request, batch_id: str | None = None) -> HTMLResponse:
    batches = _batches(require_file="crawled_products.csv")
    selected = batch_id or (batches[0] if batches else "")
    context = _base_context("ocr")
    context.update(
        {
            "batches": batches,
            "selected_batch": selected,
            "summary": _ocr_summary(selected),
            "empty_batches_hint": "crawled_products.csv가 있는 배치가 없습니다. 2단계 상세 수집을 먼저 실행하세요.",
        }
    )
    return templates.TemplateResponse(request, "step_ocr.html", context)


@app.get("/batches")
def batches(member_only: bool = True) -> dict:
    return {"batches": _batches(member_only=member_only)}


@app.get("/jobs/status", response_class=HTMLResponse)
def job_status(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/job_status.html",
        {"status": runner.status()},
    )


def _start_or_error(request: Request, step: str, command: list[str]) -> HTMLResponse:
    try:
        status = runner.start(step, command)
    except RuntimeError as error:
        status = runner.status()
        status.error = str(error)
    return templates.TemplateResponse(
        request,
        "partials/job_status.html",
        {"status": status},
    )


@app.post("/jobs/discover", response_class=HTMLResponse)
def job_discover(
    request: Request,
    mode: str = Form(...),
    batch_id: str = Form(...),
    keyword: str = Form(""),
    category_code: str = Form(""),
    category_url: str = Form(""),
    max_products: int = Form(5),
    max_scrolls: int = Form(3),
) -> HTMLResponse:
    batch_id = batch_id.strip()
    mode = mode.strip().lower()
    try:
        if mode == "urls":
            command = build_discover_urls_command(batch_id)
        elif mode == "search":
            if not keyword.strip():
                raise ValueError("검색 모드에는 keyword가 필요합니다")
            command = build_discover_search_command(
                batch_id,
                keyword.strip(),
                max_products,
                max_scrolls,
            )
        elif mode == "category":
            code = category_code.strip()
            url = category_url.strip()
            if not code and not url:
                raise ValueError("카테고리 모드에는 code 또는 url이 필요합니다")
            command = build_discover_category_command(
                batch_id,
                category_code=code or None,
                category_url=url or None,
                max_products=max_products,
                max_scrolls=max_scrolls,
            )
        else:
            raise ValueError(f"알 수 없는 모드: {mode}")
    except ValueError as error:
        status = runner.status()
        status.error = str(error)
        return templates.TemplateResponse(
            request,
            "partials/job_status.html",
            {"status": status},
        )
    return _start_or_error(request, "discover", command)


@app.post("/jobs/collect", response_class=HTMLResponse)
def job_collect(
    request: Request,
    batch_id: str = Form(...),
    force: str | None = Form(None),
) -> HTMLResponse:
    batch_id = batch_id.strip()
    discovered = get_settings().discovery_batch_dir(batch_id) / "discovered_products.csv"
    if not discovered.is_file():
        status = runner.status()
        status.error = (
            f"discovered_products.csv 없음: {discovered}. 1단계 발견을 먼저 실행하세요."
        )
        return templates.TemplateResponse(
            request, "partials/job_status.html", {"status": status}
        )
    command = build_collect_details_command(batch_id, force=bool(force))
    return _start_or_error(request, "collect", command)


@app.post("/jobs/classify", response_class=HTMLResponse)
def job_classify(
    request: Request,
    batch_id: str = Form(...),
    force: str | None = Form(None),
) -> HTMLResponse:
    batch_id = batch_id.strip()
    crawled = get_settings().discovery_batch_dir(batch_id) / "crawled_products.csv"
    if not crawled.is_file():
        status = runner.status()
        status.error = (
            f"crawled_products.csv 없음: {crawled}. 2단계 상세 수집을 먼저 실행하세요."
        )
        return templates.TemplateResponse(
            request, "partials/job_status.html", {"status": status}
        )
    command = build_classify_images_command(batch_id, force=bool(force))
    return _start_or_error(request, "classify", command)


@app.post("/jobs/ocr", response_class=HTMLResponse)
def job_ocr(request: Request, batch_id: str = Form(...)) -> HTMLResponse:
    batch_id = batch_id.strip()
    crawled = get_settings().discovery_batch_dir(batch_id) / "crawled_products.csv"
    if not crawled.is_file():
        status = runner.status()
        status.error = (
            f"crawled_products.csv 없음: {crawled}. 2단계 상세 수집을 먼저 실행하세요."
        )
        return templates.TemplateResponse(
            request, "partials/job_status.html", {"status": status}
        )
    command = build_process_batch_command(batch_id)
    return _start_or_error(request, "ocr", command)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "ok": True,
        "batch_member": settings.batch_member,
        "project_root": str(settings.project_root),
    }
