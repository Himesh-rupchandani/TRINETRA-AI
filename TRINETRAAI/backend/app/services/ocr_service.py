"""
ANPR / OCR service for uploaded CCTV videos.

Pipeline per detected vehicle:
  1. Extract plate-region crops (lower-half + full vehicle crop).
  2. Light preprocessing (upscale + grayscale + CLAHE).
  3. OCR with the best available engine (RapidOCR bundled ONNX models first,
     EasyOCR second). When no OCR engine is installed, readings come back
     empty and the plate is reported as Unknown — never invented.
  4. Normalize (uppercase, strip every non-alphanumeric) and keep only
     plate-like candidates.

Thread-safe singleton; the OCR model is loaded lazily, once per process.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import List, Optional

import cv2
import numpy as np

from ..core.config import settings
from ..core.logging_config import logger
from ..utils.plate_normalizer import normalize_plate

# Indian plate: 2 letters (state) + 1-2 digits + 0-3 letters + 3-4 digits
_INDIAN_PLATE = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{3,4}$")


@dataclass
class PlateReading:
    raw: str
    normalized: str
    confidence: float  # 0.0 - 1.0
    indian_format: bool


def _clip(x1: float, y1: float, x2: float, y2: float, w: int, h: int, pad: float = 0.0):
    bw, bh = x2 - x1, y2 - y1
    x1 -= pad * bw
    y1 -= pad * bh
    x2 += pad * bw
    y2 += pad * bh
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(w, int(x2)), min(h, int(y2))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    return x1, y1, x2, y2


def extract_plate_crops(frame: np.ndarray, bbox, vehicle_class: str = "car") -> List[np.ndarray]:
    """Candidate plate-region crops for one detected vehicle, best-first."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = (float(v) for v in bbox)
    crops: List[np.ndarray] = []
    if (vehicle_class or "car").lower() != "motorcycle":
        box = _clip(x1, y1 + (y2 - y1) * 0.45, x2, y2, w, h, pad=0.02)
        if box is not None:
            crops.append(frame[box[1]:box[3], box[0]:box[2]].copy())
    box = _clip(x1, y1, x2, y2, w, h, pad=0.05)
    if box is not None:
        crops.append(frame[box[1]:box[3], box[0]:box[2]].copy())
    return crops


def preprocess_for_ocr(crop: np.ndarray, target_width: int = 320) -> np.ndarray:
    if crop is None or crop.size == 0:
        return crop
    ch, cw = crop.shape[:2]
    if cw < target_width:
        scale = target_width / float(cw)
        crop = cv2.resize(crop, (target_width, int(ch * scale)), interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def candidate_from_text(text: str) -> Optional[str]:
    """Normalize one OCR line; return None when it is obviously not a plate."""
    if not text:
        return None
    norm = normalize_plate(text)
    if len(norm) < 6 or len(norm) > 12:
        return None
    if not any(ch.isdigit() for ch in norm):
        return None
    if not any(ch.isalpha() for ch in norm):
        return None
    return norm


class OcrService:
    """Singleton OCR wrapper with graceful degradation to Unknown plates."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._engine = None
        self._engine_name: Optional[str] = None
        self._attempted = False

    @property
    def engine_name(self) -> Optional[str]:
        self._ensure_engine()
        return self._engine_name

    @property
    def available(self) -> bool:
        if not bool(getattr(settings, "OCR_ENABLED", True)):
            return False
        self._ensure_engine()
        return self._engine is not None

    def _ensure_engine(self):
        if self._attempted:
            return self._engine
        with self._lock:
            if self._attempted:
                return self._engine
            self._attempted = True
            # RapidOCR first: models ship inside the wheel (fully offline).
            try:
                from rapidocr_onnxruntime import RapidOCR

                logger.info("[ANPR] Initializing RapidOCR (bundled ONNX models, offline)")
                self._engine = RapidOCR()
                self._engine_name = "rapidocr"
                return self._engine
            except Exception as exc:
                logger.warning(f"[ANPR] RapidOCR unavailable: {exc}")
            # EasyOCR second: needs a one-time model download.
            try:
                import easyocr  # noqa: F401
                from easyocr import Reader

                logger.info("[ANPR] Initializing EasyOCR (en, CPU)")
                self._engine = Reader(["en"], gpu=False, verbose=False)
                self._engine_name = "easyocr"
                return self._engine
            except Exception as exc:
                logger.warning(f"[ANPR] EasyOCR unavailable: {exc}")
            logger.warning(
                "[ANPR] No OCR engine installed — plates will be reported as "
                "Unknown. Install rapidocr-onnxruntime for ANPR reads."
            )
        return self._engine

    def _read_lines(self, image: np.ndarray) -> List[tuple]:
        """Raw (text, confidence) lines. Never raises."""
        engine = self._ensure_engine()
        if engine is None or image is None or getattr(image, "size", 0) == 0:
            return []
        try:
            if self._engine_name == "rapidocr":
                result, _ = engine(image)
                lines = []
                for item in result or []:
                    try:
                        _box, text, conf = item
                    except Exception:
                        continue
                    if text:
                        lines.append((str(text).strip(), float(conf)))
                return lines
            if self._engine_name == "easyocr":
                results = engine.readtext(image, detail=1, paragraph=False)
                lines = []
                for item in results or []:
                    try:
                        _box, text, conf = item
                    except Exception:
                        continue
                    if text:
                        lines.append((str(text).strip(), float(conf)))
                return lines
        except Exception as exc:
            logger.error(f"[ANPR] OCR read failed: {exc}")
        return []

    def read_plate(self, frame: np.ndarray, bbox, vehicle_class: str = "car") -> Optional[PlateReading]:
        """
        Best plate reading for one vehicle, or None when nothing plate-like
        was read. Never invents a plate.
        """
        if not self.available:
            return None
        min_conf = float(getattr(settings, "OCR_MIN_CONFIDENCE", 0.60))
        best: Optional[PlateReading] = None
        try:
            from .plate_detector import plate_crops as _plate_crops

            crops = _plate_crops(frame, bbox, vehicle_class)
        except Exception:
            crops = extract_plate_crops(frame, bbox, vehicle_class)
        if not crops:
            crops = extract_plate_crops(frame, bbox, vehicle_class)
        for crop in crops:
            if crop is None or crop.size == 0:
                continue
            # Skip tiny crops: OCR on them only produces garbage.
            if crop.shape[1] < 40 or crop.shape[0] < 12:
                continue
            prepped = preprocess_for_ocr(crop)
            for text, conf in self._read_lines(prepped):
                norm = candidate_from_text(text)
                if norm is None:
                    continue
                indian = bool(_INDIAN_PLATE.match(norm))
                # Discount implausible strings; never upgrade a weak read.
                adj = float(conf) * (1.0 if indian else 0.7)
                if adj < min_conf and not indian:
                    continue
                reading = PlateReading(raw=text, normalized=norm, confidence=float(conf), indian_format=indian)
                if best is None or reading.confidence > best.confidence:
                    best = reading
            if best is not None and best.confidence >= 0.9 and best.indian_format:
                break
        return best


# Global singleton — the OCR model is loaded once per backend process.
ocr_service = OcrService()
