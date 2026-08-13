from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .config import get_settings
from .runner import (
    JobRunner,
    build_classify_images_command,
    build_collect_details_command,
    build_dagster_intake_command,
    build_discover_category_command,
    build_discover_search_command,
    build_discover_urls_command,
    build_process_batch_command,
    build_submit_collection_command,
    build_validate_collection_command,
)
from .summaries import (
    count_csv_rows,
    infer_batch_member,
    list_discovery_batches,
    summarize_submission,
    summarize_team_batches,
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
        "platform_mode": settings.platform_mode,
        "team_members": settings.team_members,
        "active_step": active_step,
        "status": runner.status(),
    }


def _platform_admin_redirect() -> RedirectResponse | None:
    if not get_settings().platform_mode:
        return RedirectResponse(url="/", status_code=302)
    return None


def _submission_error(request: Request, message: str) -> HTMLResponse:
    status = runner.status()
    status.error = message
    return templates.TemplateResponse(
        request, "partials/job_status.html", {"status": status}
    )


def _require_platform_admin_job(request: Request) -> HTMLResponse | None:
    if get_settings().platform_mode:
        return None
    return _submission_error(request, "관리자 전용 기능입니다.")


def _batch_owner(batch_id: str) -> str:
    settings = get_settings()
    member = infer_batch_member(batch_id, settings.team_members)
    if member is None:
        raise ValueError("배치 ID에서 팀원을 식별할 수 없습니다.")
    return member


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


def _submission_summary(batch_id: str, *, member: str | None = None) -> dict | None:
    if not batch_id:
        return None
    settings = get_settings()
    owner = member or _batch_owner(batch_id)
    try:
        return summarize_submission(
            datasets_root=settings.datasets_root,
            outcome_root=settings.outcome_root,
            batch_id=batch_id,
            member=owner,
        )
    except ValueError:
        return None


def _platform_batches() -> list[str]:
    settings = get_settings()
    batches = list_discovery_batches(
        settings.discovery_root,
        require_file="crawled_products.csv",
    )
    ready: list[str] = []
    for batch_id in batches:
        try:
            owner = _batch_owner(batch_id)
        except ValueError:
            continue
        products = settings.outcome_batch_dir(batch_id, owner) / "products.csv"
        if products.is_file() and products.stat().st_size > 0:
            ready.append(batch_id)
    return ready


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


@app.get("/steps/team", response_class=HTMLResponse)
def step_team(request: Request) -> HTMLResponse:
    settings = get_settings()
    rows = summarize_team_batches(
        datasets_root=settings.datasets_root,
        outcome_root=settings.outcome_root,
        team_members=settings.team_members,
    )
    context = _base_context("team")
    context.update(
        {
            "team_rows": rows,
            "empty_team_hint": (
                "팀원 크롤 결과가 아직 없습니다. "
                "각자 1~3단계를 완료하면 여기에 표시됩니다."
            ),
        }
    )
    return templates.TemplateResponse(request, "step_team.html", context)


@app.get("/steps/platform", response_model=None)
def step_platform(
    request: Request,
) -> HTMLResponse | RedirectResponse:
    redirect = _platform_admin_redirect()
    if redirect is not None:
        return redirect
    rows = _platform_batch_rows()
    context = _base_context("platform")
    context.update(
        {
            "batch_rows": rows,
            "empty_batches_hint": (
                "OCR products.csv가 있는 팀 배치가 없습니다. "
                "팀원이 3단계 OCR을 먼저 완료해야 합니다."
            ),
        }
    )
    return templates.TemplateResponse(request, "step_platform.html", context)


@app.get("/steps/submit", response_class=RedirectResponse)
def step_submit_redirect() -> RedirectResponse:
    if not get_settings().platform_mode:
        return RedirectResponse(url="/", status_code=302)
    return RedirectResponse(url="/steps/platform", status_code=307)


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


def _start_queue_or_error(
    request: Request,
    step: str,
    commands: list[list[str]],
    *,
    labels: list[str],
    stop_on_error: bool = True,
) -> HTMLResponse:
    try:
        status = runner.start_queue(
            step,
            commands,
            progress_total=len(commands),
            labels=labels,
            stop_on_error=stop_on_error,
        )
    except (RuntimeError, ValueError) as error:
        status = runner.status()
        status.error = str(error)
    return templates.TemplateResponse(
        request,
        "partials/job_status.html",
        {"status": status},
    )


def _parse_batch_ids(batch_ids: list[str] | None) -> list[str]:
    if not batch_ids:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in batch_ids:
        for part in raw.replace(",", " ").split():
            batch_id = part.strip()
            if not batch_id or batch_id in seen:
                continue
            seen.add(batch_id)
            ordered.append(batch_id)
    return ordered


def _resolve_batch_owners(batch_ids: list[str]) -> list[tuple[str, str]]:
    resolved: list[tuple[str, str]] = []
    for batch_id in batch_ids:
        member = _batch_owner(batch_id)
        validate_batch_selection(batch_id, member)
        resolved.append((batch_id, member))
    return resolved


def _platform_batch_rows() -> list[dict]:
    settings = get_settings()
    rows = summarize_team_batches(
        datasets_root=settings.datasets_root,
        outcome_root=settings.outcome_root,
        team_members=settings.team_members,
    )
    return [
        row
        for row in rows
        if row["products"] > 0
    ]


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


@app.post("/jobs/validate-submission", response_class=HTMLResponse)
def job_validate_submission(
    request: Request,
    batch_ids: list[str] = Form(default=[]),
    batch_id: str = Form(""),
) -> HTMLResponse:
    denied = _require_platform_admin_job(request)
    if denied is not None:
        return denied
    selected = _parse_batch_ids([*batch_ids, batch_id] if batch_id else batch_ids)
    if not selected:
        return _submission_error(request, "배치를 하나 이상 선택하세요.")
    try:
        owners = _resolve_batch_owners(selected)
    except ValueError as error:
        return _submission_error(request, str(error))
    commands = [
        build_validate_collection_command(batch, member)
        for batch, member in owners
    ]
    labels = [batch for batch, _member in owners]
    return _start_queue_or_error(
        request,
        "validate-submission",
        commands,
        labels=labels,
        stop_on_error=False,
    )


@app.post("/jobs/submit", response_class=HTMLResponse)
def job_submit(
    request: Request,
    batch_ids: list[str] = Form(default=[]),
    batch_id: str = Form(""),
) -> HTMLResponse:
    denied = _require_platform_admin_job(request)
    if denied is not None:
        return denied
    selected = _parse_batch_ids([*batch_ids, batch_id] if batch_id else batch_ids)
    if not selected:
        return _submission_error(request, "배치를 하나 이상 선택하세요.")
    try:
        owners = _resolve_batch_owners(selected)
    except ValueError as error:
        return _submission_error(request, str(error))
    commands = [
        build_submit_collection_command(batch, member)
        for batch, member in owners
    ]
    labels = [batch for batch, _member in owners]
    return _start_queue_or_error(
        request,
        "submit",
        commands,
        labels=labels,
        stop_on_error=False,
    )


@app.post("/jobs/dagster-intake", response_class=HTMLResponse)
def job_dagster_intake(
    request: Request,
    batch_ids: list[str] = Form(default=[]),
    batch_id: str = Form(""),
) -> HTMLResponse:
    denied = _require_platform_admin_job(request)
    if denied is not None:
        return denied
    selected = _parse_batch_ids([*batch_ids, batch_id] if batch_id else batch_ids)
    if not selected:
        return _submission_error(request, "배치를 하나 이상 선택하세요.")
    try:
        owners = _resolve_batch_owners(selected)
    except ValueError as error:
        return _submission_error(request, str(error))
    settings = get_settings()
    missing = [
        batch
        for batch, _member in owners
        if not (
            settings.datasets_root
            / "inbox"
            / "accepted"
            / batch
            / "manifest.json"
        ).is_file()
    ]
    if missing:
        return _submission_error(
            request,
            "accepted manifest가 없는 배치: " + ", ".join(missing),
        )
    commands = [build_dagster_intake_command(batch) for batch, _member in owners]
    labels = [batch for batch, _member in owners]
    return _start_queue_or_error(
        request,
        "dagster-intake",
        commands,
        labels=labels,
        stop_on_error=False,
    )


@app.post("/jobs/platform-pipeline", response_class=HTMLResponse)
def job_platform_pipeline(
    request: Request,
    batch_ids: list[str] = Form(default=[]),
) -> HTMLResponse:
    denied = _require_platform_admin_job(request)
    if denied is not None:
        return denied
    selected = _parse_batch_ids(batch_ids)
    if not selected:
        return _submission_error(request, "배치를 하나 이상 선택하세요.")
    try:
        owners = _resolve_batch_owners(selected)
    except ValueError as error:
        return _submission_error(request, str(error))
    commands: list[list[str]] = []
    labels: list[str] = []
    for batch, member in owners:
        commands.append(build_validate_collection_command(batch, member))
        labels.append(f"{batch}/validate")
        commands.append(build_submit_collection_command(batch, member))
        labels.append(f"{batch}/submit")
        commands.append(build_dagster_intake_command(batch))
        labels.append(f"{batch}/dagster")
    return _start_queue_or_error(
        request,
        "platform-pipeline",
        commands,
        labels=labels,
        stop_on_error=True,
    )


@app.get("/submissions/{batch_id}/validation-report", response_model=None)
def download_validation_report(batch_id: str) -> FileResponse | RedirectResponse:
    redirect = _platform_admin_redirect()
    if redirect is not None:
        return redirect
    try:
        member = _batch_owner(batch_id)
        validate_batch_selection(batch_id, member)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    path = get_settings().outcome_batch_dir(batch_id, member) / "validation_report.json"
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
