"""Plate-region detection and candidate extraction.

We do not run a dedicated plate-detector model. Instead the vehicle crop is
passed to the OCR engine, which returns *all* text regions; we then keep the
ones that look like a registration plate (right length, right character mix,
right aspect ratio). This is fast, needs no extra weights, and works because a
vehicle crop contains almost no text other than the plate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from anpr.normalizer import strip_to_alnum
from anpr.ocr import OcrEngine, OcrReading
from config.settings import Settings
from logging_setup import log_event

log = logging.getLogger("trinetra.anpr")


@dataclass
class PlateCandidate:
    """A text region on a vehicle crop that plausibly is the plate."""

    raw_text: str
    confidence: float
    normalized: str
    bbox: list[float] | None = None

    def to_dict(self) -> dict:
        return {
            "raw_text": self.raw_text,
            "normalized": self.normalized,
            "confidence": round(self.confidence, 4),
        }


def _bbox_aspect_ok(bbox) -> bool:
    """Indian plates are wide: width/height typically 2.5..6."""
    if not bbox or len(bbox) < 4:
        return True  # engine gave no geometry; do not penalise
    try:
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
    except (TypeError, IndexError):
        return True
    if height <= 0:
        return False
    ratio = width / height
    return 1.6 <= ratio <= 8.0


class PlateDetector:
    """Extracts plate candidates from a vehicle crop via OCR text regions."""

    def __init__(self, settings: Settings, ocr_engine: OcrEngine) -> None:
        self.settings = settings
        self.ocr = ocr_engine

    def find(self, crop: np.ndarray) -> list[PlateCandidate]:
        if crop is None or crop.size == 0:
            return []
        readings = self.ocr.recognize(crop)
        candidates = [self._to_candidate(r) for r in readings]
        candidates = [c for c in candidates if c is not None]
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        if candidates:
            log_event(
                log,
                "plate_candidate",
                level=logging.DEBUG,
                n=len(candidates),
                best=candidates[0].normalized,
                conf=candidates[0].confidence,
            )
        return candidates

    def best(self, crop: np.ndarray) -> PlateCandidate | None:
        found = self.find(crop)
        return found[0] if found else None

    def _to_candidate(self, reading: OcrReading) -> PlateCandidate | None:
        normalized = strip_to_alnum(reading.text)
        if not (self.settings.anpr_min_plate_len <= len(normalized) <= self.settings.anpr_max_plate_len):
            return None
        if reading.confidence < self.settings.anpr_conf_threshold:
            return None
        if not _bbox_aspect_ok(reading.bbox):
            return None
        return PlateCandidate(
            raw_text=reading.text,
            confidence=float(reading.confidence),
            normalized=normalized,
            bbox=reading.bbox,
        )
