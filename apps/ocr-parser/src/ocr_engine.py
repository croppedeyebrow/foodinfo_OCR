from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import paddle
from paddleocr import PaddleOCR

from .models import OcrTextBlock


@dataclass(slots=True)
class OcrEngineResult:
    full_text: str
    confidence: float | None
    blocks: list[OcrTextBlock]
    raw_result: Any


class PaddleOcrEngine:
    name = "PaddleOCR"

    def __init__(self, language: str = "korean") -> None:
        self.version = paddle.__version__
        self._ocr = self._create_engine(language)

    @staticmethod
    def _create_engine(language: str) -> PaddleOCR:
        try:
            return PaddleOCR(
                lang=language,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except TypeError:
            return PaddleOCR(lang=language, use_angle_cls=True, show_log=False)

    def recognize(self, image_path: Path) -> OcrEngineResult:
        if hasattr(self._ocr, "predict"):
            results = list(self._ocr.predict(input=str(image_path)))
            return self._parse_v3_results(results)

        results = self._ocr.ocr(str(image_path), cls=True)
        return self._parse_legacy_results(results)

    def _parse_v3_results(self, results: list[Any]) -> OcrEngineResult:
        blocks: list[OcrTextBlock] = []
        serializable_results: list[Any] = []

        for result in results:
            payload = self._to_serializable(result)
            serializable_results.append(payload)
            data = payload.get("res", payload) if isinstance(payload, dict) else {}
            texts = data.get("rec_texts", [])
            scores = data.get("rec_scores", [])
            polygons = data.get("rec_polys", data.get("dt_polys", []))

            for index, text in enumerate(texts):
                score = self._safe_index(scores, index)
                polygon = self._safe_index(polygons, index)
                blocks.append(
                    OcrTextBlock(
                        text=str(text),
                        confidence=float(score) if score is not None else None,
                        polygon=self._normalize_polygon(polygon),
                    )
                )

        return self._build_result(blocks, serializable_results)

    def _parse_legacy_results(self, results: Any) -> OcrEngineResult:
        blocks: list[OcrTextBlock] = []
        pages = results or []

        for page in pages:
            for line in page or []:
                if not isinstance(line, (list, tuple)) or len(line) < 2:
                    continue
                polygon, recognition = line[0], line[1]
                if not isinstance(recognition, (list, tuple)) or not recognition:
                    continue
                text = str(recognition[0])
                confidence = float(recognition[1]) if len(recognition) > 1 else None
                blocks.append(
                    OcrTextBlock(
                        text=text,
                        confidence=confidence,
                        polygon=self._normalize_polygon(polygon),
                    )
                )

        return self._build_result(blocks, results)

    @staticmethod
    def _build_result(blocks: list[OcrTextBlock], raw_result: Any) -> OcrEngineResult:
        texts = [block.text.strip() for block in blocks if block.text.strip()]
        scores = [block.confidence for block in blocks if block.confidence is not None]
        confidence = sum(scores) / len(scores) if scores else None
        return OcrEngineResult(
            full_text="\n".join(texts),
            confidence=confidence,
            blocks=blocks,
            raw_result=raw_result,
        )

    @staticmethod
    def _to_serializable(result: Any) -> Any:
        value = getattr(result, "json", result)
        if callable(value):
            value = value()
        if hasattr(value, "tolist"):
            return value.tolist()
        return value

    @staticmethod
    def _safe_index(values: Iterable[Any], index: int) -> Any | None:
        try:
            return values[index]  # type: ignore[index]
        except (IndexError, KeyError, TypeError):
            return None

    @staticmethod
    def _normalize_polygon(value: Any) -> list[list[float]] | None:
        if value is None:
            return None
        if hasattr(value, "tolist"):
            value = value.tolist()
        try:
            return [[float(x), float(y)] for x, y in value]
        except (TypeError, ValueError):
            return None
