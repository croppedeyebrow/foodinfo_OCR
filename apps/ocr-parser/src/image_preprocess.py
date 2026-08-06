from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PIL import Image


DEFAULT_OCR_MAX_IMAGE_SIDE = 1600


def ocr_max_image_side() -> int:
    raw = os.getenv("OCR_MAX_IMAGE_SIDE", str(DEFAULT_OCR_MAX_IMAGE_SIDE)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_OCR_MAX_IMAGE_SIDE
    return max(0, value)


def prepare_image_for_ocr(
    image_path: Path,
    *,
    max_side: int | None = None,
) -> tuple[Path, bool]:
    """Return an OCR input path.

    If the longest side exceeds ``max_side``, write a resized JPEG temp file and
    return ``(temp_path, True)``. Caller must delete the temp file when done.
    Hash/dedupe must still use the original ``image_path``.
    """
    limit = ocr_max_image_side() if max_side is None else max_side
    if limit <= 0:
        return image_path, False

    with Image.open(image_path) as image:
        width, height = image.size
        longest = max(width, height)
        if longest <= limit:
            return image_path, False

        scale = limit / float(longest)
        new_size = (
            max(1, int(width * scale)),
            max(1, int(height * scale)),
        )
        resized = image.convert("RGB").resize(new_size, Image.Resampling.BILINEAR)
        handle = tempfile.NamedTemporaryFile(
            prefix="ocr_resize_",
            suffix=".jpg",
            delete=False,
        )
        temp_path = Path(handle.name)
        handle.close()
        resized.save(temp_path, format="JPEG", quality=85, optimize=True)
        return temp_path, True
