from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image


class TextPresence(str, Enum):
    HAS_TEXT = "HAS_TEXT"
    NO_TEXT = "NO_TEXT"
    UNKNOWN = "UNKNOWN"


class DetectMethod(str, Enum):
    HEURISTIC = "HEURISTIC"
    PADDLE_PREPASS = "PADDLE_PREPASS"


@dataclass(slots=True)
class TextPresenceResult:
    text_presence: TextPresence
    detect_method: DetectMethod
    confidence: float | None
    notes: str = ""


class OcrPrepassEngine(Protocol):
    def recognize(self, image_path: Path) -> object: ...


# 휴리스틱 점수 임계값 (엣지 밀도 기반, 0~1 스케일)
HEURISTIC_LOW = 0.04
HEURISTIC_HIGH = 0.12
PADDLE_MIN_BLOCKS = 2
PADDLE_MIN_CONFIDENCE = 0.5


def _load_gray_array(image_path: Path) -> np.ndarray:
    with Image.open(image_path) as image:
        gray = image.convert("L")
        # 판별용으로 긴 변 최대 640으로 축소
        max_side = max(gray.size)
        if max_side > 640:
            scale = 640 / max_side
            gray = gray.resize(
                (max(1, int(gray.size[0] * scale)), max(1, int(gray.size[1] * scale))),
                Image.Resampling.BILINEAR,
            )
        return np.asarray(gray, dtype=np.float32)


def heuristic_text_score(image_path: Path) -> float:
    """그레이스케일 Sobel 엣지 밀도로 텍스트 후보 점수를 추정한다 (0~1)."""
    arr = _load_gray_array(image_path)
    if arr.size == 0:
        return 0.0
    # 간단한 Sobel
    gx = np.zeros_like(arr)
    gy = np.zeros_like(arr)
    gx[:, 1:-1] = arr[:, 2:] - arr[:, :-2]
    gy[1:-1, :] = arr[2:, :] - arr[:-2, :]
    magnitude = np.sqrt(gx * gx + gy * gy)
    # 강한 엣지 비율
    threshold = max(30.0, float(np.percentile(magnitude, 75)))
    edge_ratio = float(np.mean(magnitude > threshold))
    # 대비(표준편차)도 약하게 반영
    contrast = float(np.std(arr) / 255.0)
    score = min(1.0, edge_ratio * 2.5 + contrast * 0.3)
    return score


def classify_by_heuristic(image_path: Path) -> TextPresenceResult | None:
    """확실한 구간만 판정하고, 애매하면 None을 반환한다."""
    score = heuristic_text_score(image_path)
    if score < HEURISTIC_LOW:
        return TextPresenceResult(
            text_presence=TextPresence.NO_TEXT,
            detect_method=DetectMethod.HEURISTIC,
            confidence=round(1.0 - score, 4),
            notes=f"heuristic_score={score:.4f}",
        )
    if score > HEURISTIC_HIGH:
        return TextPresenceResult(
            text_presence=TextPresence.HAS_TEXT,
            detect_method=DetectMethod.HEURISTIC,
            confidence=round(score, 4),
            notes=f"heuristic_score={score:.4f}",
        )
    return None


def classify_by_paddle_prepass(
    image_path: Path,
    engine: OcrPrepassEngine,
) -> TextPresenceResult:
    result = engine.recognize(image_path)
    blocks = getattr(result, "blocks", []) or []
    confidence = getattr(result, "confidence", None)
    full_text = (getattr(result, "full_text", None) or "").strip()
    block_count = len([b for b in blocks if getattr(b, "text", "").strip()])
    conf_value = float(confidence) if confidence is not None else 0.0

    if block_count >= PADDLE_MIN_BLOCKS and conf_value >= PADDLE_MIN_CONFIDENCE:
        presence = TextPresence.HAS_TEXT
    elif block_count == 0 or not full_text:
        presence = TextPresence.NO_TEXT
    elif conf_value >= PADDLE_MIN_CONFIDENCE:
        presence = TextPresence.HAS_TEXT
    else:
        presence = TextPresence.UNKNOWN

    return TextPresenceResult(
        text_presence=presence,
        detect_method=DetectMethod.PADDLE_PREPASS,
        confidence=round(conf_value, 4) if confidence is not None else None,
        notes=f"blocks={block_count}",
    )


def classify_image_text_presence(
    image_path: Path,
    *,
    engine: OcrPrepassEngine | None = None,
) -> TextPresenceResult:
    """하이브리드 판별: 휴리스틱 → 애매하면 Paddle 프리패스."""
    if not image_path.is_file():
        return TextPresenceResult(
            text_presence=TextPresence.UNKNOWN,
            detect_method=DetectMethod.HEURISTIC,
            confidence=None,
            notes="image_not_found",
        )

    heuristic = classify_by_heuristic(image_path)
    if heuristic is not None:
        return heuristic

    if engine is None:
        # Paddle 없이 애매 구간이면 UNKNOWN (폴백)
        score = heuristic_text_score(image_path)
        return TextPresenceResult(
            text_presence=TextPresence.UNKNOWN,
            detect_method=DetectMethod.HEURISTIC,
            confidence=round(score, 4),
            notes=f"ambiguous_without_paddle score={score:.4f}",
        )

    try:
        return classify_by_paddle_prepass(image_path, engine)
    except Exception as error:  # noqa: BLE001 - Mac segfault 등 대비 폴백
        score = heuristic_text_score(image_path)
        # 애매 구간에서 엔진 실패 시 보수적으로 HAS_TEXT에 가깝게 두지 않고 UNKNOWN
        return TextPresenceResult(
            text_presence=TextPresence.UNKNOWN,
            detect_method=DetectMethod.HEURISTIC,
            confidence=round(score, 4),
            notes=f"paddle_failed:{error}",
        )
