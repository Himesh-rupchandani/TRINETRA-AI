"""
Number-plate LOCALISATION stage (new).

Before this module the ANPR pipeline had no plate detector at all: OCR was run
on the lower half of the whole vehicle box, so on CCTV footage the plate
occupied ~1-2 % of the pixels handed to the recogniser. This module inserts the
missing ``vehicle -> plate box`` stage of the pipeline:

    vehicle detection -> tracking -> **plate detection** -> crop ->
    preprocessing -> OCR -> normalisation -> identity record

Two backends, tried in order:

1. **Learned detector** — a fine-tuned Ultralytics model at
   ``PLATE_MODEL_PATH`` (default ``models/plate_detector.pt``), trained by
   ``training/train_plate_detector.py`` on frames extracted from the user's own
   footage. Used when the weights file exists.
2. **Classical OpenCV proposal** — blackhat morphology + Sobel + adaptive
   threshold + contour filtering by aspect ratio / relative area, which is how
   plate regions were found before deep detectors existed. Always available,
   needs no weights, and is dramatically better than a fixed geometric crop.

If both produce nothing the caller falls back to the legacy heuristic crop, so
this module can only ever *add* accuracy — never remove existing behaviour.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import List, Optional, Sequence

import cv2
import numpy as np

from ..core.config import settings
from ..core.logging_config import logger
from .rfdetr_detector import rfdetr_detector


@dataclass
class PlateBox:
    """A candidate plate region in absolute frame pixel coordinates."""

    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float
    source: str  # "model" | "classical" | "heuristic"

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    @property
    def area(self) -> int:
        return self.width * self.height

    def as_list(self) -> List[int]:
        return [self.x1, self.y1, self.x2, self.y2]


def _clip(x1, y1, x2, y2, w, h, pad_x: float = 0.0, pad_y: float = 0.0):
    bw, bh = x2 - x1, y2 - y1
    x1 -= pad_x * bw
    x2 += pad_x * bw
    y1 -= pad_y * bh
    y2 += pad_y * bh
    x1, y1 = max(0, int(round(x1))), max(0, int(round(y1)))
    x2, y2 = min(w, int(round(x2))), min(h, int(round(y2)))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    return x1, y1, x2, y2


class PlateDetectorService:
    """Thread-safe singleton. The learned model (when present) loads once."""

    def __init__(self) -> None:
        self._model = None
        self._model_lock = threading.Lock()
        self._model_attempted = False
        self._model_path: Optional[str] = None

    # ------------------------------------------------------------- learned
    def _resolve_model_path(self) -> Optional[str]:
        configured = (getattr(settings, "PLATE_MODEL_PATH", "") or "").strip()
        if not configured:
            return None
        if os.path.isfile(configured):
            return configured
        backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        candidate = os.path.join(backend_root, configured)
        return candidate if os.path.isfile(candidate) else None

    def _ensure_model(self):
        # ``_model_attempted`` flips only after the load finishes (see the same
        # note in ocr_service): parallel analysis workers must not take the
        # fast path while the model is still being constructed.
        if self._model_attempted:
            return self._model
        with self._model_lock:
            if self._model_attempted:
                return self._model
            try:
                path = self._resolve_model_path()
                if not path:
                    logger.info(
                        "[PLATE] No fine-tuned plate detector found "
                        f"(PLATE_MODEL_PATH={getattr(settings, 'PLATE_MODEL_PATH', '')!r}); "
                        "using the classical OpenCV plate proposer."
                    )
                    return None
                try:
                    from ultralytics import YOLO  # lazy heavy import

                    logger.info(f"[PLATE] Loading fine-tuned plate detector: {path}")
                    model = YOLO(path)
                    imgsz = int(getattr(settings, "PLATE_DETECTION_IMGSZ", 320))
                    model.predict(
                        np.zeros((imgsz, imgsz, 3), dtype=np.uint8),
                        verbose=False, imgsz=imgsz, device="cpu",
                    )
                    self._model = model
                    self._model_path = path
                except Exception as exc:
                    logger.warning(f"[PLATE] Could not load plate detector ({exc}); using classical proposer.")
            finally:
                self._model_attempted = True
        return self._model

    @property
    def model_name(self) -> str:
        self._ensure_model()
        return os.path.basename(self._model_path) if self._model_path else "opencv-classical"

    # -------------------------------------------------------------- public
    def detect(
        self,
        frame: np.ndarray,
        vehicle_bbox: Sequence[float],
        vehicle_class: str = "car",
        max_candidates: int = 3,
    ) -> List[PlateBox]:
        """
        Return plate-region candidates (best first) inside one vehicle box,
        in absolute frame coordinates. Never raises.
        """
        if frame is None or getattr(frame, "size", 0) == 0:
            return []
        h, w = frame.shape[:2]
        box = _clip(*[float(v) for v in vehicle_bbox], w, h, pad_x=0.03, pad_y=0.03)
        if box is None:
            return []
        vx1, vy1, vx2, vy2 = box
        crop = frame[vy1:vy2, vx1:vx2]
        if crop.size == 0:
            return []

        # Priority: a fine-tuned RF-DETR plate model, then a fine-tuned YOLO
        # plate model, then the dependency-free classical proposer, then a
        # geometric guess. Each stage is tried only if the one before it
        # produced nothing, so adding a backend can only ever add accuracy.
        boxes = self._detect_rfdetr(crop, vx1, vy1)
        if not boxes:
            boxes = self._detect_model(crop, vx1, vy1)
        if not boxes:
            boxes = self._detect_classical(crop, vx1, vy1, vehicle_class)
        if not boxes:
            boxes = self._heuristic(vx1, vy1, vx2, vy2, vehicle_class)
        boxes.sort(key=lambda b: -b.confidence)
        return boxes[:max_candidates]

    # ------------------------------------------------------------ backends
    def _detect_rfdetr(self, crop: np.ndarray, ox: int, oy: int) -> List[PlateBox]:
        """
        Fine-tuned RF-DETR plate detector, when ``PLATE_RFDETR_MODEL_PATH``
        points at a checkpoint. No checkpoint configured → ``[]`` and the
        caller falls through to the next stage (behaviour unchanged).
        """
        try:
            raw = rfdetr_detector.detect_plates(crop)
        except Exception as exc:
            logger.error(f"[PLATE] RF-DETR plate inference failed: {exc}")
            return []
        return [
            PlateBox(
                x1=int(x1) + ox, y1=int(y1) + oy,
                x2=int(x2) + ox, y2=int(y2) + oy,
                confidence=float(c), source="rfdetr",
            )
            for x1, y1, x2, y2, c in raw
        ]

    def _detect_model(self, crop: np.ndarray, ox: int, oy: int) -> List[PlateBox]:
        model = self._ensure_model()
        if model is None:
            return []
        conf = float(getattr(settings, "PLATE_CONF_THRESHOLD", 0.25))
        imgsz = int(getattr(settings, "PLATE_DETECTION_IMGSZ", 320))
        try:
            results = model.predict(crop, verbose=False, conf=conf, imgsz=imgsz, device="cpu")
        except Exception as exc:
            logger.error(f"[PLATE] Plate model inference failed: {exc}")
            return []
        out: List[PlateBox] = []
        if not results or results[0].boxes is None:
            return out
        b = results[0].boxes
        for xyxy, c in zip(b.xyxy.cpu().numpy(), b.conf.cpu().numpy()):
            out.append(
                PlateBox(
                    x1=int(xyxy[0]) + ox, y1=int(xyxy[1]) + oy,
                    x2=int(xyxy[2]) + ox, y2=int(xyxy[3]) + oy,
                    confidence=float(c), source="model",
                )
            )
        return out

    @staticmethod
    def _detect_classical(crop: np.ndarray, ox: int, oy: int, vehicle_class: str) -> List[PlateBox]:
        """
        Classical plate-region proposal.

        Number plates are bright, high-contrast, wide rectangles densely packed
        with vertical strokes. Blackhat/tophat morphology + a Sobel-x response
        + a wide closing kernel isolate exactly that texture.
        """
        try:
            ch, cw = crop.shape[:2]
            if ch < 24 or cw < 24:
                return []
            # Work at a fixed width so kernel sizes behave consistently.
            scale = 320.0 / float(cw) if cw < 320 else 1.0
            work = cv2.resize(crop, (int(cw * scale), int(ch * scale)), interpolation=cv2.INTER_CUBIC) \
                if scale != 1.0 else crop
            gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
            gray = cv2.bilateralFilter(gray, 7, 45, 45)

            rect_k = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 5))
            sq_k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

            blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, rect_k)
            tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, rect_k)
            texture = cv2.max(blackhat, tophat)

            grad = cv2.Sobel(texture, cv2.CV_32F, 1, 0, ksize=3)
            grad = np.absolute(grad)
            gmin, gmax = float(grad.min()), float(grad.max())
            if gmax - gmin < 1e-6:
                return []
            grad = ((grad - gmin) / (gmax - gmin) * 255.0).astype(np.uint8)

            grad = cv2.GaussianBlur(grad, (5, 5), 0)
            grad = cv2.morphologyEx(grad, cv2.MORPH_CLOSE, rect_k)
            _, thresh = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, sq_k, iterations=2)
            thresh = cv2.erode(thresh, None, iterations=1)
            thresh = cv2.dilate(thresh, None, iterations=2)

            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            wh, ww = work.shape[:2]
            frame_area = float(wh * ww)
            # Motorcycle plates are near-square; car/truck plates are wide.
            min_ar, max_ar = (0.9, 6.5) if (vehicle_class or "").lower() == "motorcycle" else (1.6, 7.5)

            out: List[PlateBox] = []
            for cnt in contours:
                x, y, bw, bh = cv2.boundingRect(cnt)
                if bh < 8 or bw < 16:
                    continue
                ar = bw / float(bh)
                if not (min_ar <= ar <= max_ar):
                    continue
                rel = (bw * bh) / frame_area
                if rel < 0.0015 or rel > 0.35:
                    continue
                # Plates sit on the lower 2/3 of a vehicle in practically every
                # traffic camera geometry.
                if (y + bh / 2.0) < wh * 0.28:
                    continue
                roi = thresh[y:y + bh, x:x + bw]
                fill = float(roi.mean()) / 255.0 if roi.size else 0.0
                if fill < 0.25:
                    continue
                # Heuristic score: prefer plate-like aspect, lower placement, dense texture.
                ar_score = 1.0 - min(abs(ar - 3.2) / 3.2, 1.0)
                pos_score = (y + bh / 2.0) / float(wh)
                score = 0.45 * ar_score + 0.3 * pos_score + 0.25 * fill
                inv = 1.0 / scale if scale != 1.0 else 1.0
                out.append(
                    PlateBox(
                        x1=int(x * inv) + ox, y1=int(y * inv) + oy,
                        x2=int((x + bw) * inv) + ox, y2=int((y + bh) * inv) + oy,
                        confidence=round(min(0.99, max(0.05, score)), 4),
                        source="classical",
                    )
                )
            out.sort(key=lambda b: -b.confidence)
            return out[:5]
        except Exception as exc:
            logger.debug(f"[PLATE] classical proposal failed: {exc}")
            return []

    @staticmethod
    def _heuristic(vx1: int, vy1: int, vx2: int, vy2: int, vehicle_class: str) -> List[PlateBox]:
        """Legacy fallback: the lower part of the vehicle box (pre-existing behaviour)."""
        vh = vy2 - vy1
        top = vy1 + int(vh * (0.55 if (vehicle_class or "").lower() != "motorcycle" else 0.45))
        if vy2 - top < 6:
            top = vy1
        return [PlateBox(vx1, top, vx2, vy2, confidence=0.05, source="heuristic")]


plate_detector_service = PlateDetectorService()
