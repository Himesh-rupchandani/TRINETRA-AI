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

import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

from ..core.config import settings
from ..core.logging_config import logger
from ..utils.plate_normalizer import INDIAN_PLATE_RE, normalize_plate

# Canonical Indian plate (single definition, shared with the pipeline, cv-engine
# and the frontend): 2 state letters + 1-2 RTO digits + 1-3 series letters +
# 3-4 number digits. This stage used to allow ZERO series letters, so a
# letterless string like "GJ011234" counted as a proper plate here while the
# pipeline rejected it — the two layers disagreed on the same OCR read.
_INDIAN_PLATE = INDIAN_PLATE_RE


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


def upscale_plate(crop: np.ndarray, target_height: int = 64, max_scale: float = 6.0) -> np.ndarray:
    """
    Super-resolution for small/far plates.

    CCTV plates are often 12-25 px tall — far below what any OCR recogniser can
    read. We upscale to ``target_height`` with Lanczos (best for text edges)
    and follow with a mild unsharp mask, which recovers stroke separation
    without amplifying sensor noise the way a plain bicubic zoom does.
    """
    if crop is None or crop.size == 0:
        return crop
    h, w = crop.shape[:2]
    if h <= 0 or w <= 0:
        return crop
    if h >= target_height:
        return crop
    scale = min(max_scale, target_height / float(h))
    out = cv2.resize(crop, (max(8, int(w * scale)), max(8, int(h * scale))),
                     interpolation=cv2.INTER_LANCZOS4)
    blurred = cv2.GaussianBlur(out, (0, 0), 1.2)
    return cv2.addWeighted(out, 1.6, blurred, -0.6, 0)


def preprocess_variants(crop: np.ndarray) -> List[np.ndarray]:
    """
    Several preprocessing variants of one plate crop, best-effort first.

    Different plate conditions (dirty, glare, motion blur, yellow commercial
    plates, night IR) respond to different enhancements, so the pipeline OCRs a
    few cheap variants and keeps the highest-confidence *plate-shaped* read.
    All variants are returned as 3-channel BGR because both OCR engines expect
    that.
    """
    if crop is None or crop.size == 0:
        return []
    base = upscale_plate(crop)
    variants: List[np.ndarray] = []
    try:
        gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    except Exception:
        return [base]

    # 1. Raw colour crop — the most faithful input. Enhancement is a fallback
    #    for plates the raw pixels cannot resolve, never an override: CLAHE/Otsu
    #    on a small plate measurably flipped digits (0<->9, 6<->8) that the raw
    #    crop read correctly.
    variants.append(base)

    # 2. CLAHE-equalised grayscale — lifts low-contrast / night plates.
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    variants.append(cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR))

    # 3. Denoised + Otsu binarisation — strongest for clean, well-lit plates.
    den = cv2.bilateralFilter(clahe, 5, 40, 40)
    _, otsu = cv2.threshold(den, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    # White characters on dark plates: invert when the frame is mostly dark.
    if float(otsu.mean()) < 110:
        otsu = cv2.bitwise_not(otsu)
    variants.append(cv2.cvtColor(otsu, cv2.COLOR_GRAY2BGR))
    return variants


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


def joined_plate_candidate(lines) -> Optional[Tuple[str, str, float]]:
    """Reconstruct a plate that OCR split into several text regions of ONE crop.

    RapidOCR returns its text regions in reading order (top-to-bottom), which
    for a single Indian plate is also left-to-right. When no individual line is
    a valid plate by itself, the whole line set is joined and re-validated, so
    ``"GJ03P" + "08696"`` becomes ``"GJ03P08696"`` instead of being discarded
    line by line. Only genuine OCR output is combined - nothing is invented.

    Returns ``(raw_joined, normalized, mean_confidence)`` or ``None``.
    """
    if not lines or len(lines) < 2:
        return None
    texts = [str(t).strip() for t, _c in lines if str(t).strip()]
    if len(texts) < 2:
        return None
    joined = "".join(texts)
    norm = candidate_from_text(joined)
    if norm is None:
        return None
    confs = [float(c) for t, c in lines if str(t).strip() and c is not None]
    conf = sum(confs) / len(confs) if confs else 0.0
    return " ".join(texts), norm, conf


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
        # NOTE: ``_attempted`` is flipped only *after* the engine has finished
        # loading, and always inside the lock. Setting it first would let a
        # second thread (the analysis workers run several videos in parallel)
        # take the fast path while the engine is still None and wrongly
        # conclude that no OCR engine is installed — every plate in that video
        # would then be filed as Unknown.
        if self._attempted:
            return self._engine
        with self._lock:
            if self._attempted:
                return self._engine
            try:
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
            finally:
                self._attempted = True
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

    def read_lines(self, image: np.ndarray) -> List[tuple]:
        """Public accessor for raw (text, confidence) OCR lines on one image."""
        return self._read_lines(image)

    def read_plate(self, frame: np.ndarray, bbox, vehicle_class: str = "car") -> Optional[PlateReading]:
        """
        Best plate reading for one vehicle, or None when nothing plate-like
        was read. Never invents a plate.
        """
        if not self.available:
            return None
        min_conf = float(getattr(settings, "OCR_MIN_CONFIDENCE", 0.60))
        best: Optional[PlateReading] = None
        for crop in extract_plate_crops(frame, bbox, vehicle_class):
            if crop is None or crop.size == 0:
                continue
            # Skip tiny crops: OCR on them only produces garbage.
            if crop.shape[1] < 40 or crop.shape[0] < 12:
                continue
            prepped = preprocess_for_ocr(crop)
            lines = self._read_lines(prepped)
            for text, conf in lines:
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
            # A plate OCR split into two regions is one plate, not two lines:
            # try the joined reading before giving up on this crop.
            joined = joined_plate_candidate(lines)
            if joined is not None:
                raw, norm, conf = joined
                indian = bool(_INDIAN_PLATE.match(norm))
                adj = float(conf) * (1.0 if indian else 0.7)
                if adj >= min_conf:
                    reading = PlateReading(raw=raw, normalized=norm, confidence=conf, indian_format=indian)
                    if best is None or reading.confidence > best.confidence:
                        best = reading
            if best is not None and best.confidence >= 0.9 and best.indian_format:
                break
        return best


# Global singleton — the OCR model is loaded once per backend process.
ocr_service = OcrService()
