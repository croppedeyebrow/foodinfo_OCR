from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
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
    build_submit_collection_command,
    build_validate_collection_command,
)
from .summaries import (
    count_csv_rows,
    list_discovery_batches,
    summarize_submission,
    summarize_text_checks,
    validate_batch_selection,
)

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


def _submission_summary(batch_id: str) -> dict | None:
    if not batch_id:
        return None
    settings = get_settings()
    try:
        return summarize_submission(
            datasets_root=settings.datasets_root,
            outcome_root=settings.outcome_root,
            batch_id=batch_id,
            member=settings.batch_member,
        )
    except ValueError:
        return None


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


@app.get("/steps/submit", response_class=HTMLResponse)
def step_submit(request: Request, batch_id: str | None = None) -> HTMLResponse:
    batches = _batches(require_file="crawled_products.csv")
    selected = batch_id or (batches[0] if batches else "")
    context = _base_context("submit")
    context.update(
        {
            "batches": batches,
            "selected_batch": selected,
            "summary": _submission_summary(selected),
            "empty_batches_hint": (
                "crawled_products.csv가 있는 배치가 없습니다. "
                "기존 1~3단계를 먼저 완료하세요."
            ),
        }
    )
    return templates.TemplateResponse(request, "step_submit.html", context)


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


def _start_or_error(
    request: Request,
    step: str,
    command: list[str],
    *,
    progress_total: int | None = None,
) -> HTMLResponse:
    try:
        status = runner.start(step, command, progress_total=progress_total)
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
            progress_total = None
        elif mode == "search":
            if not keyword.strip():
                raise ValueError("검색 모드에는 keyword가 필요합니다")
            command = build_discover_search_command(
                batch_id,
                keyword.strip(),
                max_products,
                max_scrolls,
            )
            progress_total = max_products
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
            progress_total = max_products
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
    return _start_or_error(
        request, "discover", command, progress_total=progress_total
    )


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
    total = count_csv_rows(discovered).row_count
    return _start_or_error(request, "collect", command, progress_total=total)


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
    total = count_csv_rows(crawled).row_count
    return _start_or_error(request, "classify", command, progress_total=total)


@app.post("/jobs/ocr", response_class=HTMLResponse)
def job_ocr(
    request: Request,
    batch_id: str = Form(...),
    offset: int = Form(0),
    limit: str = Form(""),
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
    limit_value: int | None = None
    if str(limit).strip():
        try:
            limit_value = int(str(limit).strip())
            if limit_value < 1:
                raise ValueError
        except ValueError:
            status = runner.status()
            status.error = "limit은 1 이상의 정수여야 합니다."
            return templates.TemplateResponse(
                request, "partials/job_status.html", {"status": status}
            )
    if offset < 0:
        status = runner.status()
        status.error = "offset은 0 이상이어야 합니다."
        return templates.TemplateResponse(
            request, "partials/job_status.html", {"status": status}
        )

    command = build_process_batch_command(
        batch_id, offset=offset, limit=limit_value
    )
    total = count_csv_rows(crawled).row_count
    if limit_value is not None:
        total = min(max(0, total - offset), limit_value)
    elif offset:
        total = max(0, total - offset)
    return _start_or_error(request, "ocr", command, progress_total=total)


def _submission_error(request: Request, message: str) -> HTMLResponse:
    status = runner.status()
    status.error = message
    return templates.TemplateResponse(
        request, "partials/job_status.html", {"status": status}
    )


@app.post("/jobs/validate-submission", response_class=HTMLResponse)
def job_validate_submission(
    request: Request,
    batch_id: str = Form(...),
) -> HTMLResponse:
    settings = get_settings()
    batch_id = batch_id.strip()
    try:
        validate_batch_selection(batch_id, settings.batch_member)
    except ValueError as error:
        return _submission_error(request, str(error))
    command = build_validate_collection_command(batch_id, settings.batch_member)
    return _start_or_error(request, "validate-submission", command)


@app.post("/jobs/submit", response_class=HTMLResponse)
def job_submit(
    request: Request,
    batch_id: str = Form(...),
) -> HTMLResponse:
    settings = get_settings()
    batch_id = batch_id.strip()
    try:
        validate_batch_selection(batch_id, settings.batch_member)
    except ValueError as error:
        return _submission_error(request, str(error))
    command = build_submit_collection_command(batch_id, settings.batch_member)
    return _start_or_error(request, "submit", command)


@app.get("/submissions/{batch_id}/validation-report")
def download_validation_report(batch_id: str) -> FileResponse:
    settings = get_settings()
    try:
        validate_batch_selection(batch_id, settings.batch_member)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    path = (
        settings.outcome_batch_dir(batch_id)
        / "validation_report.json"
    )
    if not path.is_file():
        raise HTTPException(status_code=404, detail="validation report not found")
    return FileResponse(
        path,
        media_type="application/json",
        filename=f"{batch_id}-validation-report.json",
    )


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "ok": True,
        "batch_member": settings.batch_member,
        "project_root": str(settings.project_root),
    }
