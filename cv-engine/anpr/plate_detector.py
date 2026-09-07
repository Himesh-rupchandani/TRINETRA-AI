"""
Plate region extraction & preprocessing (spec §15, §16).

Three stages, tried in order. A plate box is NEVER turned into a plate
string here — OCR (and the confidence gate) still have to read it.

1. Dedicated plate YOLO (models/trained/plates/best.pt) when present.
2. Morphology / contour search on the vehicle crop (no extra weights).
3. Legacy heuristic crops: lower-half of the vehicle + padded full crop.

Preprocessing is deliberately light (grayscale + CLAHE + moderate upscale)
to stay real-time on CPU.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

from detection.model_paths import resolve_plate_model_path

logger = logging.getLogger("cv_engine.anpr")

Crop = np.ndarray  # BGR image


@dataclass
class PlateRegion:
    """A candidate plate box in full-frame pixel coordinates."""

    bbox: List[int]          # [x1, y1, x2, y2] in the original frame
    crop: Crop
    confidence: float
    source: str              # "yolo" | "morphology" | "heuristic"


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


# ---------------------------------------------------------------------------
# Stage 2: morphology plate search (no extra model)
# ---------------------------------------------------------------------------

def morphology_plate_boxes(
    crop: np.ndarray,
    min_area_frac: float = 0.004,
    max_area_frac: float = 0.18,
) -> List[Tuple[int, int, int, int, float]]:
    """
    Find plate-like rectangles inside a BGR vehicle crop.

    Indian plates are high-contrast (white/yellow on a dark bumper) with
    aspect ratio ~2–5. Returns (x1, y1, x2, y2, score) in crop coordinates.
    Empty list is a valid, honest miss — never invent a box.
    """
    if crop is None or crop.size == 0:
        return []
    h, w = crop.shape[:2]
    if w < 40 or h < 20:
        return []

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    # Vertical edges dominate plate characters; a black-hat also pops light plates.
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    sobel = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
    sobel = np.abs(sobel)
    sobel = (sobel / (sobel.max() + 1e-6) * 255).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 5))
    closed = cv2.morphologyEx(sobel, cv2.MORPH_CLOSE, kernel)
    closed = cv2.morphologyEx(closed, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3)))
    _, binary = cv2.threshold(closed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area_img = float(w * h)
    out: List[Tuple[int, int, int, int, float]] = []
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bh < 8 or bw < 16:
            continue
        aspect = bw / float(bh)
        if aspect < 1.6 or aspect > 6.5:
            continue
        area = bw * bh
        frac = area / area_img
        if frac < min_area_frac or frac > max_area_frac:
            continue
        # Plates sit in the lower ~70% of a car/truck/bus; motorcycles vary.
        cy = y + bh / 2.0
        if cy < 0.20 * h:
            continue
        # Prefer boxes that are actually bright (white/yellow plate).
        roi = gray[y:y + bh, x:x + bw]
        mean_luma = float(roi.mean()) if roi.size else 0.0
        if mean_luma < 70:
            continue
        # Score: aspect closeness to 4.0 (Indian plate) * relative size * brightness.
        aspect_score = 1.0 - min(abs(aspect - 4.0) / 3.0, 1.0)
        score = 0.45 * aspect_score + 0.25 * min(frac / 0.04, 1.0) + 0.30 * (mean_luma / 255.0)
        out.append((x, y, x + bw, y + bh, float(score)))
    out.sort(key=lambda t: t[4], reverse=True)
    return out[:3]


# ---------------------------------------------------------------------------
# Stage 1: optional plate YOLO
# ---------------------------------------------------------------------------

_plate_yolo = None
_plate_yolo_tried = False
_plate_yolo_path: Optional[str] = None


def _load_plate_yolo(model_path: str = ""):
    global _plate_yolo, _plate_yolo_tried, _plate_yolo_path
    if _plate_yolo_tried:
        return _plate_yolo
    _plate_yolo_tried = True
    path = resolve_plate_model_path(model_path)
    if not path:
        logger.info("[PLATE] no plate YOLO weights — using morphology + heuristic crops")
        return None
    try:
        from ultralytics import YOLO

        _plate_yolo = YOLO(path)
        _plate_yolo_path = path
        logger.info("[PLATE] loaded plate detector %s", path)
    except Exception as exc:
        logger.warning("[PLATE] could not load plate YOLO (%s) — falling back", exc)
        _plate_yolo = None
    return _plate_yolo


def reset_plate_model_cache() -> None:
    """Test helper: force the next call to re-resolve weights."""
    global _plate_yolo, _plate_yolo_tried, _plate_yolo_path
    _plate_yolo = None
    _plate_yolo_tried = False
    _plate_yolo_path = None


def _yolo_plate_boxes(crop: np.ndarray, conf: float = 0.25) -> List[Tuple[int, int, int, int, float]]:
    model = _load_plate_yolo()
    if model is None or crop is None or crop.size == 0:
        return []
    try:
        results = model.predict(crop, verbose=False, conf=conf, imgsz=640)
    except Exception as exc:
        logger.warning("[PLATE] plate YOLO inference failed: %s", exc)
        return []
    if not results or results[0].boxes is None:
        return []
    boxes = results[0].boxes
    xyxy = boxes.xyxy.cpu().numpy() if hasattr(boxes.xyxy, "cpu") else np.asarray(boxes.xyxy)
    confs = boxes.conf.cpu().numpy() if hasattr(boxes.conf, "cpu") else np.asarray(boxes.conf)
    out = []
    ch, cw = crop.shape[:2]
    for box, c in zip(xyxy, confs):
        x1, y1, x2, y2 = (int(v) for v in box)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(cw, x2), min(ch, y2)
        if x2 - x1 < 8 or y2 - y1 < 8:
            continue
        out.append((x1, y1, x2, y2, float(c)))
    out.sort(key=lambda t: t[4], reverse=True)
    return out[:3]


def detect_plate_regions(
    frame: np.ndarray,
    bbox,
    vehicle_class: str = "car",
    plate_model_path: str = "",
) -> List[PlateRegion]:
    """
    Locate plate regions for one vehicle. Empty list = no plate found
    (caller may still OCR the heuristic vehicle crop).
    """
    if frame is None or frame.size == 0 or bbox is None:
        return []
    h, w = frame.shape[:2]
    clip = _clip_bbox(bbox, w, h, pad=0.05)
    if clip is None:
        return []
    vx1, vy1, vx2, vy2 = clip
    crop = frame[vy1:vy2, vx1:vx2]
    if crop.size == 0:
        return []

    if plate_model_path:
        # Allow tests / CLI to force a path before the singleton loads.
        global _plate_yolo_tried
        if not _plate_yolo_tried:
            _load_plate_yolo(plate_model_path)

    boxes = _yolo_plate_boxes(crop)
    source = "yolo"
    if not boxes:
        boxes = morphology_plate_boxes(crop)
        source = "morphology"
    regions: List[PlateRegion] = []
    for x1, y1, x2, y2, score in boxes:
        fx1, fy1, fx2, fy2 = vx1 + x1, vy1 + y1, vx1 + x2, vy1 + y2
        plate_crop = frame[fy1:fy2, fx1:fx2].copy()
        if plate_crop.size == 0:
            continue
        regions.append(
            PlateRegion(
                bbox=[int(fx1), int(fy1), int(fx2), int(fy2)],
                crop=plate_crop,
                confidence=float(score),
                source=source,
            )
        )
    return regions


def plate_crops_for_vehicle(
    frame: np.ndarray,
    bbox,
    vehicle_class: str = "car",
) -> List[Crop]:
    """
    Best-first crops to send to OCR: detected plate boxes, then the
    legacy lower-half / full-vehicle heuristics as fallback.
    """
    crops: List[Crop] = []
    for region in detect_plate_regions(frame, bbox, vehicle_class):
        if region.crop is not None and region.crop.size > 0:
            crops.append(region.crop)
    for crop in extract_plate_candidates(frame, bbox, vehicle_class):
        crops.append(crop)
    # Dedup by shape+mean so we don't OCR the same pixels twice.
    unique: List[Crop] = []
    seen = set()
    for c in crops:
        if c is None or c.size == 0:
            continue
        key = (c.shape[0], c.shape[1], int(c.mean()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique
