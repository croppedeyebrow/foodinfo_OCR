from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .auth import is_operator, resolve_operator_batch, resolve_operator_dataset, resolve_reconcile_pair
from .config import get_settings
from .pipeline_gateway import (
    append_reconciliation_decision,
    get_pipeline_service,
    is_reference_dataset_conflict,
    pipeline_error_response,
    register_reference_dataset,
    schedule_run_execution,
    validate_reference_dataset,
)
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
    infer_batch_member,
    list_discovery_batches,
    summarize_operator_batches,
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
        "console_role": settings.console_role,
        "console_operator": settings.console_operator,
        "allowed_batch_members": settings.allowed_batch_members,
        "is_operator": is_operator(settings),
        "platform_mode": settings.platform_mode,
        "team_members": settings.team_members,
        "active_step": active_step,
        "status": runner.status(),
    }


def _operator_redirect() -> RedirectResponse | None:
    if is_operator():
        return None
    return RedirectResponse(url="/", status_code=302)


def _submission_error(request: Request, message: str, *, status_code: int = 200) -> HTMLResponse:
    status = runner.status()
    status.error = message
    return templates.TemplateResponse(
        request,
        "partials/job_status.html",
        {"status": status},
        status_code=status_code,
    )


def _require_operator_job(request: Request) -> HTMLResponse | None:
    if is_operator():
        return None
    return _submission_error(
        request,
        "OPERATOR 권한이 필요합니다.",
        status_code=403,
    )


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


@app.get("/steps/submit", response_model=None)
def step_submit(
    request: Request,
    member: str | None = None,
    include_submitted: str | None = None,
) -> HTMLResponse | RedirectResponse:
    redirect = _operator_redirect()
    if redirect is not None:
        return redirect
    settings = get_settings()
    selected_member = (member or "").strip() or None
    if selected_member and selected_member not in settings.allowed_batch_members:
        raise HTTPException(status_code=400, detail="invalid member filter")
    rows = summarize_operator_batches(
        datasets_root=settings.datasets_root,
        outcome_root=settings.outcome_root,
        allowed_members=settings.allowed_batch_members,
        member_filter=selected_member,
        include_submitted=include_submitted == "1",
    )
    context = _base_context("submit")
    context.update(
        {
            "batch_rows": rows,
            "selected_member": selected_member or "",
            "include_submitted": include_submitted == "1",
            "empty_batches_hint": (
                "OCR products.csv가 있는 미제출 배치가 없습니다. "
                "팀원이 3단계 OCR을 먼저 완료해야 합니다."
            ),
        }
    )
    return templates.TemplateResponse(request, "step_submit.html", context)


def _layer_manifest(data_root: Path, layer: str, batch_id: str) -> dict | None:
    if layer == "bronze":
        path = data_root / "bronze" / "kurly" / batch_id / "manifest.json"
    elif layer == "silver":
        path = data_root / "silver" / "kurly" / batch_id / "manifest.json"
    else:
        return None
    if not path.is_file():
        return None
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _pipeline_stage_keys() -> list[dict[str, str]]:
    service = get_pipeline_service()
    return service.list_stage_keys(stage_key_prefix="kurly_")


def _reference_stage_keys() -> list[dict[str, str]]:
    service = get_pipeline_service()
    return service.list_stage_keys(stage_key_prefix="kfia_")


def _reference_datasets() -> list[str]:
    settings = get_settings()
    inbox_root = settings.datasets_root / "reference" / "inbox"
    if not inbox_root.is_dir():
        return []
    versions: list[str] = []
    for child in sorted(inbox_root.iterdir()):
        if child.is_dir() and (child / "manifest.json").is_file():
            versions.append(child.name)
    return versions


def _reference_manifest(data_root: Path, dataset_version: str) -> dict | None:
    path = data_root / "reference" / "inbox" / dataset_version / "manifest.json"
    if not path.is_file():
        return None
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _kfia_layer_manifest(data_root: Path, layer: str, dataset_version: str) -> dict | None:
    if layer == "bronze":
        path = data_root / "bronze" / "kfia" / dataset_version / "manifest.json"
    elif layer == "silver":
        path = data_root / "silver" / "kfia" / dataset_version / "manifest.json"
    else:
        return None
    if not path.is_file():
        return None
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_pipeline_scope(batch_id: str, stage_key: str) -> tuple[str, str]:
    if stage_key == "kurly_kfia_reconcile":
        return resolve_reconcile_pair(batch_id)
    if stage_key.startswith("kfia_"):
        return resolve_operator_dataset(batch_id)
    return resolve_operator_batch(batch_id)


def _kurly_batches_with_silver() -> list[str]:
    settings = get_settings()
    silver_root = settings.datasets_root / "silver" / "kurly"
    if not silver_root.is_dir():
        return []
    batches: list[str] = []
    for child in sorted(silver_root.iterdir()):
        if child.is_dir() and (child / "manifest.json").is_file():
            batches.append(child.name)
    return batches


def _reconcile_pair_id(kurly_batch_id: str, kfia_dataset_version: str) -> str:
    return f"{kurly_batch_id}__{kfia_dataset_version}"


def _reconciled_manifest(data_root: Path, pair_id: str) -> dict | None:
    path = data_root / "reconciled" / pair_id / "manifest.json"
    if not path.is_file():
        return None
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _reconcile_stage_keys() -> list[dict[str, str]]:
    service = get_pipeline_service()
    return service.list_stage_keys(stage_key_prefix="kurly_kfia_")


@app.get("/steps/reference", response_model=None)
def step_reference(
    request: Request,
    dataset_version: str | None = None,
) -> HTMLResponse | RedirectResponse:
    redirect = _operator_redirect()
    if redirect is not None:
        return redirect
    settings = get_settings()
    datasets = _reference_datasets()
    selected = dataset_version or (datasets[-1] if datasets else "")
    status_payload = None
    stages: list[dict[str, str]] = []
    reference_manifest = None
    bronze_summary = None
    silver_summary = None
    if selected:
        try:
            resolve_operator_dataset(selected, settings=settings)
            service = get_pipeline_service()
            status_payload = service.get_batch_status(
                selected, stage_key_prefix="kfia_"
            )
            stages = _reference_stage_keys()
            reference_manifest = _reference_manifest(settings.datasets_root, selected)
            bronze_summary = _kfia_layer_manifest(
                settings.datasets_root, "bronze", selected
            )
            silver_summary = _kfia_layer_manifest(
                settings.datasets_root, "silver", selected
            )
        except Exception as error:
            status_payload = {"error": str(error)}
    context = _base_context("reference")
    context.update(
        {
            "reference_datasets": datasets,
            "selected_dataset": selected,
            "reference_status": status_payload,
            "reference_stages": stages,
            "reference_manifest": reference_manifest,
            "bronze_summary": bronze_summary,
            "silver_summary": silver_summary,
            "suggested_dataset_version": f"KFIA-{datetime.now(KST).strftime('%Y-%m')}",
        }
    )
    return templates.TemplateResponse(request, "step_reference.html", context)


@app.get("/steps/reference/partials/status/{dataset_version}", response_class=HTMLResponse)
def reference_status_partial(request: Request, dataset_version: str) -> HTMLResponse:
    redirect = _operator_redirect()
    if redirect is not None:
        return HTMLResponse("권한 없음", status_code=403)
    try:
        resolve_operator_dataset(dataset_version)
    except ValueError as error:
        return HTMLResponse(str(error), status_code=400)
    service = get_pipeline_service()
    reference_status = service.get_batch_status(
        dataset_version, stage_key_prefix="kfia_"
    )
    return templates.TemplateResponse(
        request,
        "partials/pipeline_status.html",
        {"pipeline_status": reference_status},
    )


@app.get("/steps/reconciliation", response_model=None)
def step_reconciliation(
    request: Request,
    kurly_batch_id: str | None = None,
    kfia_dataset_version: str | None = None,
) -> HTMLResponse | RedirectResponse:
    redirect = _operator_redirect()
    if redirect is not None:
        return redirect
    settings = get_settings()
    kurly_batches = _kurly_batches_with_silver()
    kfia_datasets = _reference_datasets()
    selected_kurly = kurly_batch_id or (kurly_batches[-1] if kurly_batches else "")
    selected_kfia = kfia_dataset_version or (kfia_datasets[-1] if kfia_datasets else "")
    pair_id = ""
    status_payload = None
    reconcile_summary = None
    stages: list[dict[str, str]] = []
    if selected_kurly and selected_kfia:
        pair_id = _reconcile_pair_id(selected_kurly, selected_kfia)
        try:
            resolve_reconcile_pair(pair_id, settings=settings)
            service = get_pipeline_service()
            status_payload = service.get_batch_status(
                pair_id, stage_key_prefix="kurly_kfia_"
            )
            stages = _reconcile_stage_keys()
            reconcile_summary = _reconciled_manifest(settings.datasets_root, pair_id)
        except Exception as error:
            status_payload = {"error": str(error)}
    context = _base_context("reconciliation")
    context.update(
        {
            "kurly_batches": kurly_batches,
            "kfia_datasets": kfia_datasets,
            "selected_kurly_batch": selected_kurly,
            "selected_kfia_dataset": selected_kfia,
            "pair_id": pair_id,
            "reconcile_status": status_payload,
            "reconcile_stages": stages,
            "reconcile_summary": reconcile_summary,
        }
    )
    return templates.TemplateResponse(request, "step_reconciliation.html", context)


@app.get("/steps/reconciliation/partials/status/{pair_id:path}", response_class=HTMLResponse)
def reconciliation_status_partial(request: Request, pair_id: str) -> HTMLResponse:
    redirect = _operator_redirect()
    if redirect is not None:
        return HTMLResponse("권한 없음", status_code=403)
    try:
        resolve_reconcile_pair(pair_id)
    except ValueError as error:
        return HTMLResponse(str(error), status_code=400)
    service = get_pipeline_service()
    reconcile_status = service.get_batch_status(
        pair_id, stage_key_prefix="kurly_kfia_"
    )
    return templates.TemplateResponse(
        request,
        "partials/pipeline_status.html",
        {"pipeline_status": reconcile_status},
    )


@app.get("/api/reconciliation/pairs/{pair_id:path}/review.csv")
def api_reconciliation_review_csv(pair_id: str) -> FileResponse:
    _require_operator_api()
    try:
        resolve_reconcile_pair(pair_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    settings = get_settings()
    review_path = settings.datasets_root / "reconciled" / pair_id / "review.csv"
    if not review_path.is_file():
        raise HTTPException(status_code=404, detail="review.csv not found")
    return FileResponse(
        review_path,
        media_type="text/csv",
        filename=f"reconcile_{pair_id.replace('__', '_')}_review.csv",
    )


@app.post("/api/reconciliation/decisions")
async def api_reconciliation_decision(request: Request) -> dict:
    _require_operator_api()
    import uuid
    from datetime import datetime

    body = await request.json()
    pair_id = str(body.get("pair_id") or "").strip()
    reconciled_record_id = str(body.get("reconciled_record_id") or "").strip()
    action = str(body.get("action") or "").strip()
    reason = str(body.get("reason") or "").strip()
    selected_kfia_record_id = body.get("selected_kfia_record_id")
    if not pair_id or not reconciled_record_id or not action or not reason:
        raise HTTPException(status_code=400, detail="필수 필드가 누락되었습니다.")
    try:
        _, reviewer = resolve_reconcile_pair(pair_id)
        kurly_batch_id, kfia_dataset_version = pair_id.split("__", 1)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    settings = get_settings()
    decision = {
        "schema_version": "1.0.0",
        "decision_id": str(uuid.uuid4()),
        "reconcile_pair_id": pair_id,
        "reconciled_record_id": reconciled_record_id,
        "kurly_batch_id": kurly_batch_id,
        "kfia_dataset_version": kfia_dataset_version,
        "reviewer": reviewer,
        "decided_at": datetime.now(KST).isoformat(),
        "action": action,
        "reason": reason,
        "selected_kfia_record_id": selected_kfia_record_id,
        "rule_version": "kurly_kfia_reconcile_v1.0.0",
    }
    try:
        path = append_reconciliation_decision(
            data_root=settings.datasets_root,
            pair_id=pair_id,
            decision=decision,
        )
    except Exception as error:
        status_code, payload = pipeline_error_response(error)
        raise HTTPException(status_code=status_code, detail=payload) from error
    return {"decision": decision, "path": path.as_posix()}


@app.get("/steps/pipeline", response_model=None)
def step_pipeline(
    request: Request,
    batch_id: str | None = None,
) -> HTMLResponse | RedirectResponse:
    redirect = _operator_redirect()
    if redirect is not None:
        return redirect
    settings = get_settings()
    batches = _accepted_batch_rows()
    selected = batch_id or (batches[0]["batch_id"] if batches else "")
    status_payload = None
    stages: list[dict[str, str]] = []
    bronze_summary = None
    silver_summary = None
    if selected:
        try:
            resolve_operator_batch(selected, settings=settings)
            service = get_pipeline_service()
            status_payload = service.get_batch_status(selected, stage_key_prefix="kurly_")
            stages = _pipeline_stage_keys()
            if not stages:
                raise RuntimeError(
                    "등록된 Pipeline Stage가 없습니다. console 이미지를 재빌드했는지 확인하세요."
                )
            bronze_summary = _layer_manifest(settings.datasets_root, "bronze", selected)
            silver_summary = _layer_manifest(settings.datasets_root, "silver", selected)
        except Exception as error:
            status_payload = {"error": str(error)}
    context = _base_context("pipeline")
    context.update(
        {
            "accepted_batches": batches,
            "selected_batch": selected,
            "pipeline_status": status_payload,
            "pipeline_stages": stages,
            "bronze_summary": bronze_summary,
            "silver_summary": silver_summary,
            "empty_batches_hint": (
                "accepted 제출된 배치가 없습니다. "
                "5단계 검증·제출을 먼저 완료하세요."
            ),
        }
    )
    return templates.TemplateResponse(request, "step_pipeline.html", context)


@app.get("/steps/platform", response_class=RedirectResponse, include_in_schema=False)
def step_platform_redirect() -> RedirectResponse:
    if is_operator():
        return RedirectResponse(url="/steps/pipeline", status_code=307)
    return RedirectResponse(url="/", status_code=302)


@app.get("/steps/pipeline/partials/status/{batch_id}", response_class=HTMLResponse)
def pipeline_status_partial(request: Request, batch_id: str) -> HTMLResponse:
    redirect = _operator_redirect()
    if redirect is not None:
        return HTMLResponse("권한 없음", status_code=403)
    try:
        resolve_operator_batch(batch_id)
    except ValueError as error:
        return HTMLResponse(str(error), status_code=400)
    service = get_pipeline_service()
    pipeline_status = service.get_batch_status(batch_id, stage_key_prefix="kurly_")
    return templates.TemplateResponse(
        request,
        "partials/pipeline_status.html",
        {"pipeline_status": pipeline_status},
    )


@app.get("/steps/pipeline/evidence/{batch_id}", response_model=None)
def step_pipeline_evidence(
    request: Request, batch_id: str
) -> HTMLResponse | RedirectResponse:
    redirect = _operator_redirect()
    if redirect is not None:
        return redirect
    try:
        resolve_operator_batch(batch_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    settings = get_settings()
    evidence_path = (
        settings.datasets_root / "silver" / "kurly" / batch_id / "evidence.jsonl"
    )
    if not evidence_path.is_file():
        raise HTTPException(status_code=404, detail="silver evidence not found")
    import json

    rows = [
        json.loads(line)
        for line in evidence_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    context = _base_context("pipeline")
    context.update({"batch_id": batch_id, "evidence_rows": rows})
    return templates.TemplateResponse(request, "step_pipeline_evidence.html", context)


@app.get("/api/pipeline/batches/{batch_id}/silver/review.csv")
def api_pipeline_silver_review_csv(batch_id: str) -> FileResponse:
    _require_operator_api()
    try:
        resolve_operator_batch(batch_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    settings = get_settings()
    review_path = (
        settings.datasets_root / "silver" / "kurly" / batch_id / "review.csv"
    )
    if not review_path.is_file():
        raise HTTPException(status_code=404, detail="silver review.csv not found")
    return FileResponse(
        review_path,
        media_type="text/csv",
        filename=f"{batch_id}-review.csv",
    )


@app.get("/steps/submit-legacy", response_class=RedirectResponse, include_in_schema=False)
def step_submit_legacy_redirect() -> RedirectResponse:
    if is_operator():
        return RedirectResponse(url="/steps/submit", status_code=307)
    return RedirectResponse(url="/", status_code=302)


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


def _resolve_operator_batches(batch_ids: list[str]) -> list[tuple[str, str]]:
    resolved: list[tuple[str, str]] = []
    for batch_id in batch_ids:
        resolved.append(resolve_operator_batch(batch_id))
    return resolved


def _accepted_batch_rows() -> list[dict]:
    settings = get_settings()
    rows = summarize_team_batches(
        datasets_root=settings.datasets_root,
        outcome_root=settings.outcome_root,
        team_members=settings.allowed_batch_members,
    )
    return [row for row in rows if row["accepted"]]


def _require_operator_api() -> None:
    if not is_operator():
        raise HTTPException(status_code=403, detail="OPERATOR role required")


@app.post("/api/reference/datasets/{dataset_version}/register")
async def api_reference_register(
    dataset_version: str,
    export_file: UploadFile = File(...),
) -> dict:
    _require_operator_api()
    try:
        _dataset_version, _member = resolve_operator_dataset(dataset_version)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    settings = get_settings()
    import tempfile

    suffix = Path(export_file.filename or "export.csv").suffix or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
        content = await export_file.read()
        temporary.write(content)
        temp_path = Path(temporary.name)
    try:
        result = register_reference_dataset(
            data_root=settings.datasets_root,
            dataset_version=_dataset_version,
            export_path=temp_path,
            registered_by=settings.console_operator,
        )
        return {
            "dataset_version": result.dataset_version,
            "row_count": result.row_count,
            "duplicate": result.duplicate,
            "manifest": result.manifest,
        }
    except Exception as error:
        if is_reference_dataset_conflict(error):
            raise HTTPException(status_code=409, detail=str(error)) from error
        status_code, payload = pipeline_error_response(error)
        raise HTTPException(status_code=status_code, detail=payload) from error
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/api/reference/datasets/{dataset_version}/validate")
def api_reference_validate(dataset_version: str) -> dict:
    _require_operator_api()
    try:
        _dataset_version, _member = resolve_operator_dataset(dataset_version)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    settings = get_settings()
    try:
        return validate_reference_dataset(
            data_root=settings.datasets_root,
            dataset_version=_dataset_version,
        )
    except Exception as error:
        status_code, payload = pipeline_error_response(error)
        raise HTTPException(status_code=status_code, detail=payload) from error


@app.post("/api/pipeline/batches/{batch_id}/stages/{stage_key}/runs")
def api_pipeline_start_run(batch_id: str, stage_key: str) -> dict:
    _require_operator_api()
    try:
        _batch_id, member = _resolve_pipeline_scope(batch_id, stage_key)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        service = get_pipeline_service()
        snapshot = service.start_run(
            batch_id=_batch_id,
            member=member,
            stage_key=stage_key,
        )
        schedule_run_execution(run_id=str(snapshot["run_id"]), member=member)
        return snapshot
    except Exception as error:
        status_code, payload = pipeline_error_response(error)
        raise HTTPException(status_code=status_code, detail=payload) from error


@app.get("/api/pipeline/runs/{run_id}")
def api_pipeline_get_run(run_id: str) -> dict:
    _require_operator_api()
    service = get_pipeline_service()
    snapshot = service.get_run(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="run not found")
    return snapshot


@app.get("/api/pipeline/batches/{batch_id}/status")
def api_pipeline_batch_status(batch_id: str) -> dict:
    _require_operator_api()
    try:
        resolve_operator_batch(batch_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    service = get_pipeline_service()
    return service.get_batch_status(batch_id)


@app.post("/api/pipeline/runs/{run_id}/retry")
def api_pipeline_retry_run(run_id: str) -> dict:
    _require_operator_api()
    service = get_pipeline_service()
    snapshot = service.get_run(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="run not found")
    batch_id = str(snapshot.get("batch_id") or "")
    stage_key = ""
    steps = snapshot.get("steps") or []
    if steps:
        stage_key = str(steps[-1].get("step_key") or "")
    try:
        _batch_id, member = _resolve_pipeline_scope(batch_id, stage_key)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        new_snapshot = service.retry_run(run_id, member=member)
        schedule_run_execution(
            run_id=str(new_snapshot["run_id"]),
            member=member,
        )
        return new_snapshot
    except Exception as error:
        status_code, payload = pipeline_error_response(error)
        raise HTTPException(status_code=status_code, detail=payload) from error


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
    denied = _require_operator_job(request)
    if denied is not None:
        return denied
    selected = _parse_batch_ids([*batch_ids, batch_id] if batch_id else batch_ids)
    if not selected:
        return _submission_error(request, "배치를 하나 이상 선택하세요.")
    try:
        owners = _resolve_operator_batches(selected)
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
    denied = _require_operator_job(request)
    if denied is not None:
        return denied
    selected = _parse_batch_ids([*batch_ids, batch_id] if batch_id else batch_ids)
    if not selected:
        return _submission_error(request, "배치를 하나 이상 선택하세요.")
    try:
        owners = _resolve_operator_batches(selected)
    except ValueError as error:
        return _submission_error(request, str(error))
    operator = get_settings().console_operator
    commands = [
        build_submit_collection_command(batch, member, submitted_by=operator)
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


@app.get("/submissions/{batch_id}/validation-report", response_model=None)
def download_validation_report(batch_id: str) -> FileResponse | RedirectResponse:
    redirect = _operator_redirect()
    if redirect is not None:
        return redirect
    try:
        _batch_id, member = resolve_operator_batch(batch_id)
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
