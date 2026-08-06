from __future__ import annotations

from pathlib import Path

from conftest import use_app
from PIL import Image


def test_prepare_image_for_ocr_skips_small_image(tmp_path: Path) -> None:
    use_app("ocr-parser")
    from src.image_preprocess import prepare_image_for_ocr

    path = tmp_path / "small.jpg"
    Image.new("RGB", (800, 600), color=(20, 20, 20)).save(path)
    out, is_temp = prepare_image_for_ocr(path, max_side=1600)
    assert out == path
    assert is_temp is False


def test_prepare_image_for_ocr_resizes_large_image(tmp_path: Path) -> None:
    use_app("ocr-parser")
    from src.image_preprocess import prepare_image_for_ocr

    path = tmp_path / "large.jpg"
    Image.new("RGB", (4000, 2000), color=(40, 40, 40)).save(path)
    out, is_temp = prepare_image_for_ocr(path, max_side=1600)
    assert is_temp is True
    assert out != path
    with Image.open(out) as resized:
        assert max(resized.size) == 1600
    out.unlink(missing_ok=True)


def test_prepare_image_disable_with_zero(tmp_path: Path) -> None:
    use_app("ocr-parser")
    from src.image_preprocess import prepare_image_for_ocr

    path = tmp_path / "large.jpg"
    Image.new("RGB", (3000, 3000), color=(1, 1, 1)).save(path)
    out, is_temp = prepare_image_for_ocr(path, max_side=0)
    assert out == path
    assert is_temp is False
