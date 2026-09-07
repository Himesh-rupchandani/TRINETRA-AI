"""
Number-plate region detector used by the backend ANPR path.

Does NOT invent a plate string. It only returns BGR crops that OCR may
read; empty result means "no plate region found".
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from ..core.config import settings
from ..core.logging_config import logger


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _repo_root() -> Path:
    # TRINETRAAI/backend/app/services -> hack/
    return Path(__file__).resolve().parents[4]


def resolve_plate_weights() -> Optional[str]:
    configured = (getattr(settings, "PLATE_MODEL_PATH", "") or "").strip()
    candidates = []
    if configured:
        candidates.append(Path(configured))
        if not os.path.isabs(configured):
            candidates.append(_backend_root() / configured)
            candidates.append(_repo_root() / "cv-engine" / configured)
    candidates.extend(
        [
            _backend_root() / "models" / "trained" / "plates" / "best.pt",
            _repo_root() / "cv-engine" / "models" / "trained" / "plates" / "best.pt",
        ]
    )
    for p in candidates:
        try:
            if p.is_file() and p.stat().st_size > 1024:
                return str(p.resolve())
        except OSError:
            continue
    return None


_plate_model = None
_plate_tried = False


def _load_plate_model():
    global _plate_model, _plate_tried
    if _plate_tried:
        return _plate_model
    _plate_tried = True
    path = resolve_plate_weights()
    if not path:
        return None
    try:
        from ultralytics import YOLO

        _plate_model = YOLO(path)
        logger.info(f"[PLATE] loaded plate detector {path}")
    except Exception as exc:
        logger.warning(f"[PLATE] plate YOLO unavailable ({exc}); morphology fallback")
        _plate_model = None
    return _plate_model


def morphology_plate_boxes(crop: np.ndarray) -> List[Tuple[int, int, int, int, float]]:
    """Plate-like rectangles inside a vehicle crop. Empty = honest miss."""
    if crop is None or crop.size == 0:
        return []
    h, w = crop.shape[:2]
    if w < 40 or h < 20:
        return []
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    sobel = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
    sobel = np.abs(sobel)
    sobel = (sobel / (sobel.max() + 1e-6) * 255).astype(np.uint8)
    closed = cv2.morphologyEx(
        sobel, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (17, 5))
    )
    closed = cv2.morphologyEx(
        closed, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
    )
    _, binary = cv2.threshold(closed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area_img = float(w * h)
    out = []
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bh < 8 or bw < 16:
            continue
        aspect = bw / float(bh)
        if aspect < 1.6 or aspect > 6.5:
            continue
        frac = (bw * bh) / area_img
        if frac < 0.004 or frac > 0.18:
            continue
        if (y + bh / 2.0) < 0.20 * h:
            continue
        roi = gray[y:y + bh, x:x + bw]
        mean_luma = float(roi.mean()) if roi.size else 0.0
        if mean_luma < 70:
            continue
        aspect_score = 1.0 - min(abs(aspect - 4.0) / 3.0, 1.0)
        score = 0.45 * aspect_score + 0.25 * min(frac / 0.04, 1.0) + 0.30 * (mean_luma / 255.0)
        out.append((x, y, x + bw, y + bh, float(score)))
    out.sort(key=lambda t: t[4], reverse=True)
    return out[:3]


def plate_crops(frame: np.ndarray, bbox, vehicle_class: str = "car") -> List[np.ndarray]:
    """Best-first plate crops for one vehicle (YOLO plate → morphology → heuristic)."""
    if frame is None or frame.size == 0 or bbox is None:
        return []
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = (float(v) for v in bbox)
    pad_x, pad_y = 0.05 * (x2 - x1), 0.05 * (y2 - y1)
    vx1, vy1 = max(0, int(x1 - pad_x)), max(0, int(y1 - pad_y))
    vx2, vy2 = min(w, int(x2 + pad_x)), min(h, int(y2 + pad_y))
    if vx2 - vx1 < 8 or vy2 - vy1 < 8:
        return []
    crop = frame[vy1:vy2, vx1:vx2]
    boxes: List[Tuple[int, int, int, int, float]] = []
    model = _load_plate_model()
    if model is not None and crop.size > 0:
        try:
            results = model.predict(crop, verbose=False, conf=0.25, imgsz=640)
            if results and results[0].boxes is not None:
                xyxy = results[0].boxes.xyxy.cpu().numpy()
                confs = results[0].boxes.conf.cpu().numpy()
                for box, c in zip(xyxy, confs):
                    bx1, by1, bx2, by2 = (int(v) for v in box)
                    boxes.append((bx1, by1, bx2, by2, float(c)))
        except Exception as exc:
            logger.warning(f"[PLATE] plate YOLO inference failed: {exc}")
    if not boxes:
        boxes = morphology_plate_boxes(crop)

    crops: List[np.ndarray] = []
    for bx1, by1, bx2, by2, _ in boxes:
        fx1 = max(0, vx1 + bx1)
        fy1 = max(0, vy1 + by1)
        fx2 = min(w, vx1 + bx2)
        fy2 = min(h, vy1 + by2)
        if fx2 - fx1 >= 16 and fy2 - fy1 >= 8:
            crops.append(frame[fy1:fy2, fx1:fx2].copy())

    # Heuristic fallback: lower-half (not motorcycles) + full vehicle.
    if (vehicle_class or "car").lower() != "motorcycle":
        ly1 = max(0, int(y1 + (y2 - y1) * 0.45))
        if int(x2) - int(x1) >= 8 and int(y2) - ly1 >= 8:
            crops.append(frame[ly1:int(y2), max(0, int(x1)):min(w, int(x2))].copy())
    crops.append(crop.copy())
    return crops
