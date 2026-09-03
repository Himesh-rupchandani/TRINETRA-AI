"""OCR engines for plate text.

Two engines behind one interface:

* :class:`RapidOcrEngine` — PP-OCR (PaddleOCR) models shipped *inside the
  wheel*, so it works with no network access and is fast on CPU. Default.
* :class:`EasyOcrEngine` — EasyOCR (CRAFT detector + CRNN). The weights are
  downloaded from GitHub on first use, so this engine is for machines with a
  normal network.

``OCR_ENGINE`` selects one explicitly; ``auto`` prefers RapidOCR because it is
the only engine that is guaranteed offline. Neither may crash the pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np

from config.settings import Settings
from logging_setup import log_event

log = logging.getLogger("trinetra.anpr.ocr")


@dataclass(frozen=True)
class OcrReading:
    """One line of text found by an OCR engine on a crop."""

    text: str
    confidence: float
    bbox: list[float] | None = None  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]

    @property
    def length(self) -> int:
        return len(self.text)


class OcrEngine:
    name = "base"

    def recognize(self, crop: np.ndarray) -> list[OcrReading]:  # pragma: no cover
        raise NotImplementedError


class RapidOcrEngine(OcrEngine):
    name = "rapidocr"

    def __init__(self) -> None:
        self._ocr = None

    def _engine(self):
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR

            self._ocr = RapidOCR()
        return self._ocr

    @staticmethod
    def available() -> bool:
        try:
            import rapidocr_onnxruntime  # noqa: F401

            return True
        except Exception:  # noqa: BLE001
            return False

    def recognize(self, crop: np.ndarray) -> list[OcrReading]:
        if crop is None or crop.size == 0:
            return []
        try:
            result, _ = self._engine()(crop)
        except Exception as exc:  # noqa: BLE001 - never take the pipeline down
            log_event(log, "ocr_error", level=logging.WARNING, engine=self.name, error=str(exc))
            return []
        if not result:
            return []
        readings = []
        for item in result:
            box, text, conf = item[0], item[1], float(item[2])
            readings.append(OcrReading(text=str(text), confidence=conf, bbox=[list(map(float, p)) for p in box]))
        return readings


class EasyOcrEngine(OcrEngine):
    name = "easyocr"

    def __init__(self, languages: Iterable[str] = ("en",), gpu: bool = False) -> None:
        self._languages = list(languages)
        self._gpu = gpu
        self._reader = None

    def _engine(self):
        if self._reader is None:
            import easyocr

            self._reader = easyocr.Reader(self._languages, gpu=self._gpu, verbose=False)
        return self._reader

    @staticmethod
    def available() -> bool:
        try:
            import easyocr  # noqa: F401

            return True
        except Exception:  # noqa: BLE001
            return False

    def recognize(self, crop: np.ndarray) -> list[OcrReading]:
        if crop is None or crop.size == 0:
            return []
        try:
            result = self._engine().readtext(crop, detail=1)
        except Exception as exc:  # noqa: BLE001
            log_event(log, "ocr_error", level=logging.WARNING, engine=self.name, error=str(exc))
            return []
        return [
            OcrReading(text=str(text), confidence=float(conf), bbox=[list(map(float, p)) for p in box])
            for box, text, conf in result
        ]


def get_ocr_engine(settings: Settings) -> Optional[OcrEngine]:
    """Instantiate the engine named by ``settings.ocr_engine`` (or auto-pick)."""
    choice = (settings.ocr_engine or "auto").lower()
    if choice == "none":
        return None
    candidates = (
        [RapidOcrEngine(), EasyOcrEngine(settings.ocr_languages, settings.ocr_gpu)]
        if choice == "auto"
        else {
            "easyocr": [EasyOcrEngine(settings.ocr_languages, settings.ocr_gpu)],
            "rapidocr": [RapidOcrEngine()],
        }[choice]
    )
    for engine in candidates:
        if engine.name == "easyocr" and EasyOcrEngine.available():
            return engine
        if engine.name == "rapidocr" and RapidOcrEngine.available():
            return engine
    log_event(log, "ocr_engine_unavailable", level=logging.ERROR, requested=choice)
    return None
