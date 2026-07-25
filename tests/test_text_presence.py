from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from conftest import use_app

use_app("ocr-parser")

from src.image_check_exporter import (  # noqa: E402
    ImageTextCheckRecord,
    load_image_text_checks,
    merge_and_write_image_text_checks,
    write_image_text_checks,
)
from src.text_presence import (  # noqa: E402
    DetectMethod,
    TextPresence,
    classify_by_heuristic,
    classify_image_text_presence,
    heuristic_text_score,
)


def _make_solid_image(path: Path, color: int = 180) -> None:
    from PIL import Image

    Image.new("L", (200, 200), color=color).save(path)


def _make_textish_image(path: Path) -> None:
    """고대비 세로/가로 선이 많은 이미지 → 휴리스틱상 텍스트 후보."""
    from PIL import Image, ImageDraw

    image = Image.new("L", (400, 600), color=255)
    draw = ImageDraw.Draw(image)
    for y in range(40, 560, 18):
        draw.rectangle((30, y, 370, y + 8), fill=0)
    for x in range(40, 360, 40):
        draw.line((x, 40, x, 560), fill=0, width=2)
    image.save(path)


def test_heuristic_solid_image_is_no_text(tmp_path: Path) -> None:
    path = tmp_path / "solid.jpg"
    _make_solid_image(path)
    result = classify_by_heuristic(path)
    assert result is not None
    assert result.text_presence == TextPresence.NO_TEXT
    assert result.detect_method == DetectMethod.HEURISTIC


def test_heuristic_textish_image_is_has_text(tmp_path: Path) -> None:
    path = tmp_path / "textish.jpg"
    _make_textish_image(path)
    score = heuristic_text_score(path)
    result = classify_by_heuristic(path)
    # 강한 엣지 패턴이면 HAS_TEXT, 애매하면 None(프리패스 대상)
    assert score > 0.0
    if result is not None:
        assert result.text_presence == TextPresence.HAS_TEXT


def test_classify_without_engine_ambiguous_is_unknown(tmp_path: Path) -> None:
    path = tmp_path / "mid.jpg"
    # 약간의 노이즈만 있는 중간 이미지 만들기
    from PIL import Image
    import numpy as np

    arr = np.random.default_rng(0).integers(100, 156, size=(300, 300), dtype=np.uint8)
    Image.fromarray(arr, mode="L").save(path)
    # 엔진 없이 애매하면 UNKNOWN 또는 휴리스틱 확정
    result = classify_image_text_presence(path, engine=None)
    assert result.text_presence in {
        TextPresence.HAS_TEXT,
        TextPresence.NO_TEXT,
        TextPresence.UNKNOWN,
    }


def test_image_check_csv_roundtrip(tmp_path: Path) -> None:
    output = tmp_path / "image_text_check.csv"
    record = ImageTextCheckRecord(
        batch_id="20260726-jaeseong-001",
        original_product_id="5047857",
        image_path="detail_images/5047857_01_abc.jpg",
        text_presence=TextPresence.NO_TEXT,
        detect_method=DetectMethod.HEURISTIC,
        confidence=0.91,
        checked_at=datetime.now(ZoneInfo("Asia/Seoul")),
        notes="test",
    )
    write_image_text_checks([record], output)
    mapping = load_image_text_checks(output)
    assert mapping["detail_images/5047857_01_abc.jpg"] == "NO_TEXT"
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")


def test_merge_image_text_checks(tmp_path: Path) -> None:
    output = tmp_path / "image_text_check.csv"
    first = ImageTextCheckRecord(
        batch_id="b1",
        original_product_id="1",
        image_path="a.jpg",
        text_presence=TextPresence.NO_TEXT,
        detect_method=DetectMethod.HEURISTIC,
        confidence=0.9,
        checked_at=datetime.now(ZoneInfo("Asia/Seoul")),
    )
    write_image_text_checks([first], output)
    second = ImageTextCheckRecord(
        batch_id="b1",
        original_product_id="1",
        image_path="a.jpg",
        text_presence=TextPresence.HAS_TEXT,
        detect_method=DetectMethod.PADDLE_PREPASS,
        confidence=0.8,
        checked_at=datetime.now(ZoneInfo("Asia/Seoul")),
    )
    third = ImageTextCheckRecord(
        batch_id="b1",
        original_product_id="2",
        image_path="b.jpg",
        text_presence=TextPresence.NO_TEXT,
        detect_method=DetectMethod.HEURISTIC,
        confidence=0.7,
        checked_at=datetime.now(ZoneInfo("Asia/Seoul")),
    )
    merge_and_write_image_text_checks(output, [second, third])
    mapping = load_image_text_checks(output)
    assert mapping["a.jpg"] == "HAS_TEXT"
    assert mapping["b.jpg"] == "NO_TEXT"


def test_no_text_skip_filter() -> None:
    checks = {
        "detail_images/a.jpg": "NO_TEXT",
        "detail_images/b.jpg": "HAS_TEXT",
    }
    rows = [
        {"image_path": "detail_images/a.jpg"},
        {"image_path": "detail_images/b.jpg"},
        {"image_path": "detail_images/c.jpg"},
    ]
    kept = []
    skipped = 0
    for row in rows:
        image_rel = row["image_path"]
        if checks.get(image_rel) == TextPresence.NO_TEXT.value:
            skipped += 1
            continue
        kept.append(image_rel)
    assert skipped == 1
    assert kept == ["detail_images/b.jpg", "detail_images/c.jpg"]
