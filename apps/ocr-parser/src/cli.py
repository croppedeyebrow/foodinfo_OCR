from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import paddle
import typer
from paddleocr import PaddleOCR

from .batch_filter import batch_belongs_to_member
from .exporter import append_failure_csv
from .image_check_exporter import (
    ImageTextCheckRecord,
    image_check_csv_path,
    load_checked_image_paths,
    load_image_text_checks,
    merge_and_write_image_text_checks,
)
from .models import FailureRecord, ProductInput
from .pipeline import ProductOcrPipeline
from .text_presence import TextPresence, classify_image_text_presence

app = typer.Typer(no_args_is_help=True)
KST = ZoneInfo("Asia/Seoul")


@app.command()
def health() -> None:
    """PaddlePaddle, PaddleOCR 및 데이터 볼륨을 확인한다."""
    input_dir = Path("/data/images")
    output_dir = Path("/data/ocr_output")
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    typer.echo("OCR parser container OK")
    typer.echo(f"PaddlePaddle version: {paddle.__version__}")
    typer.echo(f"PaddleOCR class: {PaddleOCR.__name__}")
    typer.echo(f"Input directory: {input_dir}")
    typer.echo(f"Output directory: {output_dir}")


@app.command("process-one")
def process_one(
    batch_id: str = typer.Option(..., "--batch-id"),
    product_id: str = typer.Option(..., "--product-id"),
    product_name: str = typer.Option(..., "--product-name"),
    product_url: str = typer.Option(..., "--product-url"),
    image_path: str = typer.Option(..., "--image"),
    source_image_url: str | None = typer.Option(None, "--source-image-url"),
    data_root: Path = typer.Option(Path("/data"), "--data-root"),
) -> None:
    """상품 이미지 한 건을 OCR하고 원문 JSON과 배치 CSV를 생성한다."""
    product = ProductInput(
        batch_id=batch_id,
        original_product_id=product_id,
        product_name=product_name,
        product_url=product_url,
        image_path=image_path,
        source_image_url=source_image_url,
    )
    pipeline = ProductOcrPipeline(
        parser_version=os.getenv("PARSER_VERSION", "0.1.0"),
        language=os.getenv("OCR_LANGUAGE", "korean"),
    )
    raw_path, csv_path = pipeline.process(product, data_root)
    typer.echo(f"Raw JSON: {raw_path}")
    typer.echo(f"Batch CSV: {csv_path}")


@app.command("classify-images")
def classify_images(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        exists=True,
        help="배치별 crawled_products.csv",
    ),
    batch_id: str = typer.Option(..., "--batch-id"),
    data_root: Path = typer.Option(Path("/data"), "--data-root"),
    force: bool = typer.Option(False, "--force", help="기존 체크 결과 재검사"),
) -> None:
    """상세 이미지의 텍스트 유무를 판별해 image_text_check.csv를 생성한다."""
    member = os.getenv("BATCH_MEMBER", "unknown")
    if not batch_belongs_to_member(batch_id, member):
        typer.echo(
            f"--batch-id '{batch_id}' does not belong to BATCH_MEMBER='{member}'.",
            err=True,
        )
        raise typer.Exit(code=1)

    check_path = image_check_csv_path(data_root / "discovery", batch_id)
    already_checked = set() if force else load_checked_image_paths(check_path)

    # Paddle은 애매 구간에서만 쓰므로 lazy 초기화
    engine_holder: dict[str, object] = {"engine": None}

    def get_engine():
        if engine_holder["engine"] is None:
            from .ocr_engine import PaddleOcrEngine

            engine_holder["engine"] = PaddleOcrEngine(
                language=os.getenv("OCR_LANGUAGE", "korean")
            )
        return engine_holder["engine"]

    new_records: list[ImageTextCheckRecord] = []
    scanned = 0
    skipped_existing = 0
    has_text = 0
    no_text = 0
    unknown = 0

    with manifest.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            row_batch = (row.get("batch_id") or "").strip()
            if row_batch and row_batch != batch_id:
                continue
            image_rel = (row.get("image_path") or "").strip()
            if not image_rel:
                continue
            if image_rel in already_checked:
                skipped_existing += 1
                continue

            image_file = Path(image_rel)
            if not image_file.is_absolute():
                image_file = data_root / image_rel

            # 휴리스틱 먼저; 애매할 때만 엔진 생성
            from .text_presence import classify_by_heuristic

            heuristic = None
            if image_file.is_file():
                heuristic = classify_by_heuristic(image_file)

            if heuristic is not None:
                result = heuristic
            else:
                try:
                    result = classify_image_text_presence(
                        image_file,
                        engine=get_engine(),  # type: ignore[arg-type]
                    )
                except Exception as error:  # noqa: BLE001
                    result = classify_image_text_presence(image_file, engine=None)
                    result.notes = f"{result.notes};engine_init_failed:{error}"

            scanned += 1
            if result.text_presence == TextPresence.HAS_TEXT:
                has_text += 1
            elif result.text_presence == TextPresence.NO_TEXT:
                no_text += 1
            else:
                unknown += 1

            new_records.append(
                ImageTextCheckRecord(
                    batch_id=batch_id,
                    original_product_id=(row.get("original_product_id") or "").strip(),
                    image_path=image_rel,
                    text_presence=result.text_presence,
                    detect_method=result.detect_method,
                    confidence=result.confidence,
                    checked_at=datetime.now(KST),
                    notes=result.notes,
                )
            )
            already_checked.add(image_rel)
            typer.echo(
                f"{result.text_presence.value}: {image_rel} ({result.detect_method.value})"
            )

    if new_records:
        merge_and_write_image_text_checks(check_path, new_records)

    typer.echo(f"Check CSV: {check_path}")
    typer.echo(
        f"Completed: scanned={scanned}, skipped_existing={skipped_existing}, "
        f"HAS_TEXT={has_text}, NO_TEXT={no_text}, UNKNOWN={unknown}"
    )
    if scanned == 0 and skipped_existing == 0:
        typer.echo("No images found in manifest.", err=True)
        raise typer.Exit(code=1)


@app.command("process-batch")
def process_batch(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        exists=True,
        help="배치별 crawled_products.csv (예: /data/discovery/{batch_id}/crawled_products.csv)",
    ),
    batch_id: str | None = typer.Option(
        None,
        "--batch-id",
        help="처리할 배치 ID. 생략 시 BATCH_MEMBER 소속 배치만 처리",
    ),
    data_root: Path = typer.Option(Path("/data"), "--data-root"),
    offset: int = typer.Option(
        0,
        "--offset",
        min=0,
        help="OCR 대상 행 중 건너뛸 개수 (NO_TEXT 제외 후 기준)",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        min=1,
        help="이번에 처리할 최대 행 수 (NO_TEXT 제외 후 기준). 미지정 시 전부",
    ),
) -> None:
    """입력 manifest CSV의 상품을 순차 처리한다.

    기본적으로 `.env`의 BATCH_MEMBER가 들어간 batch_id 행만 처리한다.
    `--batch-id`를 주면 해당 배치만 처리한다.
    image_text_check.csv가 있으면 NO_TEXT 이미지는 OCR을 건너뛴다.
    `--offset` / `--limit`으로 OCR 대상을 청크 단위로 나눌 수 있다.
    """
    outcome_root = Path(os.getenv("OUTCOME_ROOT", "/outcome"))
    member = os.getenv("BATCH_MEMBER", "unknown")

    if batch_id is not None and not batch_belongs_to_member(batch_id, member):
        typer.echo(
            f"--batch-id '{batch_id}' does not belong to BATCH_MEMBER='{member}'.",
            err=True,
        )
        raise typer.Exit(code=1)

    # 배치별 텍스트 체크 맵 캐시
    text_checks_by_batch: dict[str, dict[str, str] | None] = {}

    def checks_for(row_batch: str) -> dict[str, str] | None:
        if row_batch not in text_checks_by_batch:
            check_file = image_check_csv_path(data_root / "discovery", row_batch)
            if check_file.exists():
                text_checks_by_batch[row_batch] = load_image_text_checks(check_file)
                typer.echo(f"Loaded text checks: {check_file}")
            else:
                text_checks_by_batch[row_batch] = None
                typer.echo(
                    f"WARNING: image_text_check.csv not found for {row_batch}; "
                    "OCR will run for all images.",
                    err=True,
                )
        return text_checks_by_batch[row_batch]

    pipeline = ProductOcrPipeline(
        parser_version=os.getenv("PARSER_VERSION", "0.2.0"),
        language=os.getenv("OCR_LANGUAGE", "korean"),
    )
    success_count = 0
    failure_count = 0
    skipped_count = 0
    filtered_out = 0
    no_text_skipped = 0

    eligible_rows: list[dict[str, str]] = []
    with manifest.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            row_batch_id = (row.get("batch_id") or "").strip()
            if batch_id is not None:
                if row_batch_id != batch_id:
                    filtered_out += 1
                    continue
            elif not batch_belongs_to_member(row_batch_id, member):
                filtered_out += 1
                continue

            image_rel = (row.get("image_path") or "").strip()
            checks = checks_for(row_batch_id) if row_batch_id else None
            if checks is not None and image_rel:
                presence = checks.get(image_rel)
                if presence == TextPresence.NO_TEXT.value:
                    no_text_skipped += 1
                    typer.echo(f"SKIP_NO_TEXT: {image_rel}")
                    continue
            eligible_rows.append(row)

    end = None if limit is None else offset + limit
    chunk_rows = eligible_rows[offset:end]
    typer.echo(
        f"Chunk: offset={offset}, limit={limit if limit is not None else 'all'}, "
        f"eligible={len(eligible_rows)}, processing={len(chunk_rows)}"
    )

    for row in chunk_rows:
        row_batch_id = (row.get("batch_id") or "").strip()
        try:
            normalized_row = {
                key: (value if value != "" else None) for key, value in row.items()
            }
            if normalized_row.get("source_site") is None:
                normalized_row["source_site"] = "KURLY"
            product = ProductInput(**normalized_row)
            raw_path, csv_path = pipeline.process(product, data_root)
            if raw_path is None:
                skipped_count += 1
            success_count += 1
            typer.echo(f"OK: {product.original_product_id} -> {csv_path}")
        except Exception as error:  # 배치 전체 중단 방지
            failure_count += 1
            fail_batch_id = row_batch_id or "UNKNOWN_BATCH"
            failure = FailureRecord(
                batch_id=fail_batch_id,
                source_site=row.get("source_site") or "KURLY",
                original_product_id=row.get("original_product_id", ""),
                product_name=row.get("product_name", ""),
                product_url=row.get("product_url", ""),
                image_path=row.get("image_path", "") or "",
                error_code=_error_code(error),
                error_message=str(error),
                failed_at=datetime.now(KST),
            )
            append_failure_csv(
                failure,
                outcome_root / member / fail_batch_id / "failures.csv",
            )
            typer.echo(f"FAILED: {failure.original_product_id}: {error}", err=True)

    if (
        success_count == 0
        and failure_count == 0
        and no_text_skipped == 0
        and not chunk_rows
    ):
        typer.echo(
            f"No rows matched. BATCH_MEMBER={member}, "
            f"batch_id={batch_id or '(member filter)'}, filtered_out={filtered_out}, "
            f"offset={offset}, limit={limit}",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(
        f"Completed: success={success_count}, failure={failure_count}, "
        f"skipped={skipped_count}, no_text_skipped={no_text_skipped}, "
        f"filtered_out={filtered_out}, offset={offset}, "
        f"limit={limit if limit is not None else 'all'}, member={member}"
    )


def _error_code(error: Exception) -> str:
    message = str(error)
    if isinstance(error, FileNotFoundError):
        return "IMAGE_NOT_FOUND"
    if "OCR_TEXT_EMPTY" in message:
        return "OCR_TEXT_EMPTY"
    if isinstance(error, ValueError):
        return "INPUT_VALIDATION_FAILED"
    return "OCR_FAILED"


if __name__ == "__main__":
    app()
