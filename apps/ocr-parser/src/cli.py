from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import paddle
import typer
from paddleocr import PaddleOCR

from .exporter import append_failure_csv
from .models import FailureRecord, ProductInput
from .pipeline import ProductOcrPipeline

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


@app.command("process-batch")
def process_batch(
    manifest: Path = typer.Option(
        Path("/data/input/crawled_products.csv"), "--manifest", exists=True
    ),
    data_root: Path = typer.Option(Path("/data"), "--data-root"),
) -> None:
    """입력 manifest CSV의 상품을 순차 처리한다."""
    outcome_root = Path(os.getenv("OUTCOME_ROOT", "/outcome"))
    member = os.getenv("BATCH_MEMBER", "unknown")

    pipeline = ProductOcrPipeline(
        parser_version=os.getenv("PARSER_VERSION", "0.2.0"),
        language=os.getenv("OCR_LANGUAGE", "korean"),
    )
    success_count = 0
    failure_count = 0
    skipped_count = 0

    with manifest.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            try:
                normalized_row = {
                    key: (value if value != "" else None) for key, value in row.items()
                }
                if normalized_row.get("source_site") is None:
                    normalized_row["source_site"] = "KURLY"
                # 기존 products.csv 호환: product_name 유지
                product = ProductInput(**normalized_row)
                raw_path, csv_path = pipeline.process(product, data_root)
                if raw_path is None and not product.image_path:
                    # DOM only 또는 중복 스킵도 성공으로 집계
                    skipped_count += 0
                success_count += 1
                typer.echo(f"OK: {product.original_product_id} -> {csv_path}")
            except Exception as error:  # 배치 전체 중단 방지
                failure_count += 1
                batch_id = row.get("batch_id", "UNKNOWN_BATCH")
                failure = FailureRecord(
                    batch_id=batch_id,
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
                    outcome_root / member / batch_id / "failures.csv",
                )
                typer.echo(f"FAILED: {failure.original_product_id}: {error}", err=True)

    typer.echo(
        f"Completed: success={success_count}, failure={failure_count}, skipped={skipped_count}"
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
