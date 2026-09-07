"""
YOLO-based licence-plate REGION detector (spec §15 — plate detection stage).

The live pipeline historically OCR'd heuristic vehicle sub-crops (lower half of
the vehicle box). That is cheap but noisy: it feeds the OCR whole bumpers,
stickers and shop signage. This module adds a real single-class plate detector
so OCR only ever sees an actual plate region, which is the single biggest
false-positive control in the whole ANPR chain (spec §20).

Design:
- The model is OPTIONAL. If the weights are missing or ultralytics is not
  installed, :meth:`YoloPlateDetector.available` is False and callers fall back
  to the existing heuristic crops — nothing breaks.
- Detection runs on the *vehicle crop*, not the full frame: the crop is
  upscaled so small/distant plates still reach the model's receptive field, and
  boxes are mapped back to full-frame coordinates.
- The detector never invents text; it only localises a region and reports the
  detector confidence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger("cv_engine.anpr.plate")


@dataclass
class PlateBox:
    """One detected plate region, in FULL-FRAME pixel coordinates."""

    bbox: List[float]          # [x1, y1, x2, y2]
    confidence: float

    @property
    def width(self) -> float:
        return max(0.0, self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> float:
        return max(0.0, self.bbox[3] - self.bbox[1])

    @property
    def area(self) -> float:
        return self.width * self.height

    def to_dict(self) -> dict:
        return {
            "bbox": [round(float(v), 2) for v in self.bbox],
            "confidence": round(float(self.confidence), 4),
            "width_px": round(self.width, 1),
            "height_px": round(self.height, 1),
        }


class YoloPlateDetector:
    """Single-class plate detector wrapping an Ultralytics model."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        conf_threshold: float = 0.25,
        imgsz: int = 320,
        device: str = "cpu",
        upscale_to: int = 320,
    ):
        self.model_path = str(model_path) if model_path else ""
        self.conf_threshold = float(conf_threshold)
        self.imgsz = int(imgsz)
        self.device = device
        self.upscale_to = int(upscale_to)
        self._model = None
        self._load_failed = False
        self.inferences = 0
        self.total_infer_ms = 0.0

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        if self._load_failed:
            return False
        if self._model is not None:
            return True
        return bool(self.model_path) and Path(self.model_path).exists()

    def _ensure_model(self):
        if self._model is not None or self._load_failed:
            return self._model
        try:
            from ultralytics import YOLO  # lazy heavy import

            logger.info("[PLATE] loading plate detector: %s", self.model_path)
            self._model = YOLO(self.model_path)
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.error("[PLATE] could not load %s: %s", self.model_path, exc)
            self._load_failed = True
            self._model = None
        return self._model

    # ------------------------------------------------------------------
    def detect_in_vehicle(
        self,
        frame: np.ndarray,
        vehicle_bbox: Sequence[float],
        pad: float = 0.04,
        max_results: int = 1,
    ) -> List[PlateBox]:
        """
        Detect plate region(s) inside one vehicle box.

        Returns boxes in FULL-FRAME coordinates, best-first. Empty list means
        "no plate detected" — callers must record NOT_DETECTED, never guess.
        """
        import cv2  # local import keeps the module importable without cv2

        if frame is None or getattr(frame, "size", 0) == 0:
            return []
        model = self._ensure_model()
        if model is None:
            return []

        h, w = frame.shape[:2]
        x1, y1, x2, y2 = [float(v) for v in vehicle_bbox]
        bw, bh = x2 - x1, y2 - y1
        x1 = max(0, int(x1 - pad * bw))
        y1 = max(0, int(y1 - pad * bh))
        x2 = min(w, int(x2 + pad * bw))
        y2 = min(h, int(y2 + pad * bh))
        if x2 - x1 < 16 or y2 - y1 < 16:
            return []

        crop = frame[y1:y2, x1:x2]
        ch, cw = crop.shape[:2]
        scale = 1.0
        if cw < self.upscale_to:
            scale = self.upscale_to / float(cw)
            crop = cv2.resize(
                crop, (int(cw * scale), int(ch * scale)), interpolation=cv2.INTER_CUBIC
            )

        import time

        t0 = time.perf_counter()
        try:
            results = model.predict(
                crop, imgsz=self.imgsz, conf=self.conf_threshold,
                device=self.device, verbose=False,
            )
        except Exception as exc:
            logger.error("[PLATE] inference failed: %s", exc)
            return []
        self.total_infer_ms += (time.perf_counter() - t0) * 1000.0
        self.inferences += 1

        out: List[PlateBox] = []
        for r in results:
            boxes = getattr(r, "boxes", None)
            if boxes is None:
                continue
            for b in boxes:
                try:
                    px1, py1, px2, py2 = [float(v) for v in b.xyxy[0].tolist()]
                    conf = float(b.conf[0])
                except Exception:
                    continue
                # crop-space -> full-frame space
                fx1 = x1 + px1 / scale
                fy1 = y1 + py1 / scale
                fx2 = x1 + px2 / scale
                fy2 = y1 + py2 / scale
                out.append(PlateBox([fx1, fy1, fx2, fy2], conf))

        out.sort(key=lambda p: -p.confidence)
        return out[:max_results]


def crop_plate(frame: np.ndarray, plate: PlateBox, pad_ratio: float = 0.08) -> Optional[np.ndarray]:
    """Cut the plate region out of the frame with a small margin."""
    if frame is None or plate is None:
        return None
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = plate.bbox
    px, py = pad_ratio * (x2 - x1), pad_ratio * (y2 - y1)
    x1, y1 = max(0, int(x1 - px)), max(0, int(y1 - py))
    x2, y2 = min(w, int(x2 + px)), min(h, int(y2 + py))
    if x2 - x1 < 8 or y2 - y1 < 6:
        return None
    return frame[y1:y2, x1:x2].copy()
