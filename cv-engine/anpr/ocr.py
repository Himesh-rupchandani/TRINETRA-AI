"""
OCR wrapper (spec §15). Uses EasyOCR (CPU) with lazy initialization.

Do NOT assume OCR output is correct — every line comes back with its own
confidence, and downstream code filters/validates candidates and aggregates
across frames instead of trusting a single read.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

logger = logging.getLogger("cv_engine.anpr")


@dataclass
class OcrLine:
    text: str
    confidence: float


class OcrEngine:
    """
    Thin wrapper around easyocr.Reader. Lazy import/init so unit tests and
    non-ANPR flows never pay the model-load cost.
    """

    def __init__(self, languages=("en",), gpu: bool = False):
        self.languages = list(languages)
        self.gpu = gpu
        self._reader = None
        self.last_read_ms: Optional[float] = None
        self.reads_performed = 0

    def _ensure_reader(self):
        if self._reader is None:
            import easyocr  # lazy heavy import

            logger.info("[OCR] initializing EasyOCR (languages=%s, gpu=%s)", self.languages, self.gpu)
            self._reader = easyocr.Reader(self.languages, gpu=self.gpu, verbose=False)
        return self._reader

    def warmup(self) -> None:
        self._ensure_reader()
        dummy = np.zeros((64, 200, 3), dtype=np.uint8)
        self.read(dummy)

    def read(self, image: np.ndarray) -> List[OcrLine]:
        """Run OCR on one image crop. Returns [] on any failure (never raises)."""
        if image is None or getattr(image, "size", 0) == 0:
            return []
        try:
            reader = self._ensure_reader()
            t0 = time.perf_counter()
            results = reader.readtext(image, detail=1, paragraph=False)
            self.last_read_ms = (time.perf_counter() - t0) * 1000.0
            self.reads_performed += 1
        except Exception as exc:
            logger.error("[OCR] read failed: %s", exc)
            return []

        lines: List[OcrLine] = []
        for item in results or []:
            try:
                _box, text, conf = item
            except Exception:
                continue
            if text:
                lines.append(OcrLine(text=text.strip(), confidence=float(conf)))
        return lines
