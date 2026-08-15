from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from conftest import use_app
from PIL import Image


def _product(image_path: str):
    from src.models import ProductInput

    return ProductInput(
        batch_id="20260814-jaeseong-001",
        original_product_id="1000001",
        product_name="용가리 치킨",
        product_url="https://www.kurly.com/goods/1000001",
        image_path=image_path,
    )


def _result(text: str):
    return SimpleNamespace(
        full_text=text,
        confidence=0.95,
        blocks=[],
        raw_result={"text": text},
    )


class _RecordingEngine:
    name = "FakeOCR"
    version = "test"

    def __init__(self, results: list[object]) -> None:
        self.results = list(results)
        self.input_sizes: list[tuple[int, int]] = []

    def recognize(self, image_path: Path):
        with Image.open(image_path) as image:
            self.input_sizes.append(image.size)
        return self.results.pop(0)


def test_gate_skips_full_ocr_for_brand_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    use_app("ocr-parser")
    from src.pipeline import ProductOcrPipeline

    image = tmp_path / "brand.jpg"
    Image.new("RGB", (1600, 1000), color=(255, 255, 255)).save(image)
    monkeypatch.setenv("OUTCOME_ROOT", str(tmp_path / "outcome"))
    monkeypatch.setenv("BATCH_MEMBER", "jaeseong")
    monkeypatch.setenv("OCR_DISCLOSURE_GATE_ENABLED", "true")
    monkeypatch.setenv("OCR_DISCLOSURE_GATE_MAX_IMAGE_SIDE", "640")
    engine = _RecordingEngine([_result("용가리 치킨")])
    pipeline = ProductOcrPipeline()
    pipeline._engine = engine

    raw_path, csv_path = pipeline.process(_product(str(image)), tmp_path)

    assert raw_path is not None and raw_path.is_file()
    assert not csv_path.exists()
    assert engine.input_sizes == [(640, 400)]


def test_gate_runs_full_ocr_for_disclosure_keyword(
    tmp_path: Path,
    monkeypatch,
) -> None:
    use_app("ocr-parser")
    from src.pipeline import ProductOcrPipeline

    image = tmp_path / "disclosure.jpg"
    Image.new("RGB", (1600, 1000), color=(255, 255, 255)).save(image)
    monkeypatch.setenv("OUTCOME_ROOT", str(tmp_path / "outcome"))
    monkeypatch.setenv("BATCH_MEMBER", "jaeseong")
    monkeypatch.setenv("OCR_DISCLOSURE_GATE_ENABLED", "true")
    monkeypatch.setenv("OCR_DISCLOSURE_GATE_MAX_IMAGE_SIDE", "640")
    engine = _RecordingEngine(
        [_result("소비기한 별도 표기"), _result("소비기한 2026-12-31 보관방법 냉동")]
    )
    pipeline = ProductOcrPipeline()
    pipeline._engine = engine

    raw_path, csv_path = pipeline.process(_product(str(image)), tmp_path)

    assert raw_path is not None and raw_path.is_file()
    assert csv_path.is_file()
    assert engine.input_sizes == [(640, 400), (1600, 1000)]


def test_gate_can_be_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    use_app("ocr-parser")
    from src.pipeline import ProductOcrPipeline

    image = tmp_path / "brand.jpg"
    Image.new("RGB", (1600, 1000), color=(255, 255, 255)).save(image)
    monkeypatch.setenv("OUTCOME_ROOT", str(tmp_path / "outcome"))
    monkeypatch.setenv("BATCH_MEMBER", "jaeseong")
    monkeypatch.setenv("OCR_DISCLOSURE_GATE_ENABLED", "false")
    engine = _RecordingEngine([_result("용가리 치킨")])
    pipeline = ProductOcrPipeline()
    pipeline._engine = engine

    raw_path, _ = pipeline.process(_product(str(image)), tmp_path)

    assert raw_path is not None and raw_path.is_file()
    assert engine.input_sizes == [(1600, 1000)]
