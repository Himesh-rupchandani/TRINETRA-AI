"""
Image-quality metrics used for evidence/best-frame selection (spec §11 of the
Faculty-Parking brief: "select the best evidence frame based on measurable
quality").

Everything here is measured from pixels — no heuristic constants pretending to
be measurements. The composite score is a weighted blend that is monotonic in
each of its inputs, so a bigger, sharper, better-read plate always wins.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np


def sharpness(image: Optional[np.ndarray]) -> float:
    """Variance of the Laplacian — the standard focus/motion-blur proxy."""
    if image is None or getattr(image, "size", 0) == 0:
        return 0.0
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def bbox_area(bbox: Optional[Sequence[float]]) -> float:
    if not bbox:
        return 0.0
    x1, y1, x2, y2 = [float(v) for v in bbox]
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def edge_distance_ratio(bbox: Sequence[float], width: int, height: int) -> float:
    """
    0.0 when the box touches a frame edge (likely truncated/occluded vehicle),
    1.0 when it sits comfortably inside the frame. Used to prefer evidence
    frames where the vehicle is fully visible.
    """
    if not bbox or width <= 0 or height <= 0:
        return 0.0
    x1, y1, x2, y2 = [float(v) for v in bbox]
    margin = min(x1, y1, width - x2, height - y2)
    ref = 0.05 * min(width, height)
    if ref <= 0:
        return 0.0
    return float(max(0.0, min(1.0, margin / ref)))


def evidence_score(
    plate_area_px: float,
    plate_sharpness: float,
    ocr_confidence: float,
    vehicle_area_px: float = 0.0,
    edge_ratio: float = 1.0,
) -> float:
    """
    Composite evidence quality in [0, ~1].

    Weights (documented, not magic): OCR confidence dominates because it is the
    only term that reflects *readability*; plate size and sharpness break ties;
    vehicle size and edge distance are weak preferences.
    """
    # Normalisers chosen from measured ranges on 720p-1080p footage:
    #   plate area 0..12000 px², sharpness 0..500, vehicle area 0..120000 px².
    a = min(1.0, max(0.0, plate_area_px) / 12000.0)
    s = min(1.0, max(0.0, plate_sharpness) / 500.0)
    o = min(1.0, max(0.0, ocr_confidence))
    v = min(1.0, max(0.0, vehicle_area_px) / 120000.0)
    e = min(1.0, max(0.0, edge_ratio))
    return round(0.45 * o + 0.25 * a + 0.15 * s + 0.10 * v + 0.05 * e, 6)
