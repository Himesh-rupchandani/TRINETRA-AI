"""
Plate region extraction & preprocessing (spec §15, §16).

Strategy (fast, no extra model): the plate is almost always on the vehicle
bounding box itself, so we OCR tightly-cropped vehicle regions. We generate
1-2 candidate crops per vehicle:

1. full vehicle crop (slightly padded),
2. lower-half crop for cars/trucks/buses (rear plates usually sit low).

Preprocessing is deliberately light (grayscale + CLAHE + moderate upscale)
to stay real-time on CPU.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

Crop = np.ndarray  # BGR image


def _clip_bbox(bbox, w: int, h: int, pad: float = 0.0) -> Optional[Tuple[int, int, int, int]]:
    x1, y1, x2, y2 = [float(v) for v in bbox]
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


def vehicle_crop(frame: np.ndarray, bbox, pad: float = 0.05) -> Optional[Crop]:
    h, w = frame.shape[:2]
    box = _clip_bbox(bbox, w, h, pad)
    if box is None:
        return None
    x1, y1, x2, y2 = box
    return frame[y1:y2, x1:x2].copy()


def extract_plate_candidates(frame: np.ndarray, bbox, vehicle_class: str = "car") -> List[Crop]:
    """
    Return candidate plate-region crops for one detected vehicle,
    ordered most-likely-first.
    """
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = [float(v) for v in bbox]
    candidates: List[Crop] = []

    # Lower-half crop (rear/front plate zone) — skip for motorcycles (plates
    # are small and position varies).
    if vehicle_class != "motorcycle":
        box = _clip_bbox([x1, y1 + (y2 - y1) * 0.45, x2, y2], w, h, pad=0.02)
        if box is not None:
            candidates.append(frame[box[1]:box[3], box[0]:box[2]].copy())

    full = vehicle_crop(frame, bbox, pad=0.05)
    if full is not None:
        candidates.append(full)

    return candidates


def preprocess_for_ocr(crop: Crop, target_width: int = 320) -> Crop:
    """
    Light OCR preprocessing: upscale small crops, grayscale + CLAHE.
    Returns a BGR image (EasyOCR accepts both; gray improves plate contrast).
    """
    if crop is None or crop.size == 0:
        return crop
    ch, cw = crop.shape[:2]
    if cw < target_width:
        scale = target_width / float(cw)
        crop = cv2.resize(crop, (target_width, int(ch * scale)), interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
