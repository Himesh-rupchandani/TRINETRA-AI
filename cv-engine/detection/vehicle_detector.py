"""
Vehicle detection with Ultralytics YOLO11 (spec §11, §12).

Design for hackathon hardware:
- yolo11s by default, configurable via MODEL_PATH.
- Fine-tuned weights at models/trained/vehicles/best.pt are preferred when
  present; the stock COCO checkpoint is kept at models/original/yolo11s.pt.
- Vehicle classes only — a class filter is passed so non-vehicle predictions
  are discarded early (COCO layout). Custom fine-tuned models already have
  a vehicle-only head, so we filter by name instead of COCO ids.
- imgsz / NMS IoU configurable; frame skipping is done upstream.
- Torch/ultralytics imports are lazy so the rest of the engine (and its unit
  tests) work without them installed.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from .classes import (
    VEHICLE_CLASS_IDS,
    VEHICLE_NAMES,
    class_name_for,
    is_coco_layout,
    normalize_vehicle_class,
)
from .model_paths import resolve_vehicle_model_path

logger = logging.getLogger("cv_engine.detection")


@dataclass
class Detection:
    """One detected vehicle in one frame (spec §11 example shape)."""

    bbox: List[float]            # [x1, y1, x2, y2] in frame pixels
    class_name: str              # car | motorcycle | bus | truck | autorickshaw
    confidence: float
    camera_id: Optional[str] = None
    pts_ms: Optional[float] = None
    class_id: int = -1

    @property
    def xyxy(self):
        return tuple(self.bbox)

    def to_dict(self) -> dict:
        return {
            "bbox": self.bbox,
            "class": self.class_name,
            "confidence": self.confidence,
            "camera_id": self.camera_id,
            "pts_ms": self.pts_ms,
        }


class VehicleDetector:
    """Thin, lazy wrapper around an Ultralytics YOLO11 model."""

    def __init__(
        self,
        model_path: str = "yolo11s.pt",
        conf_threshold: float = 0.35,
        imgsz: int = 640,
        device: str = "cpu",
        include_bicycles: bool = False,
        iou_threshold: float = 0.50,
        prefer_trained: bool = True,
    ):
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.imgsz = imgsz
        self.device = device
        self.iou_threshold = iou_threshold
        self.prefer_trained = prefer_trained
        self.include_bicycles = include_bicycles
        self.class_ids = sorted(
            list(VEHICLE_CLASS_IDS.keys()) + ([1] if include_bicycles else [])
        )
        self._model = None
        self._resolved_path: Optional[str] = None
        self._coco_layout: Optional[bool] = None
        self.last_inference_ms: Optional[float] = None
        self.frames_inferred = 0

    def _ensure_model(self):
        if self._model is None:
            from ultralytics import YOLO  # lazy: heavy import

            path = resolve_vehicle_model_path(
                self.model_path, prefer_trained=self.prefer_trained
            )
            self._resolved_path = path
            logger.info("[DETECTOR] loading YOLO model %s (device=%s)", path, self.device)
            self._model = YOLO(path)
            names = getattr(self._model, "names", {}) or {}
            self._coco_layout = is_coco_layout(names)
            logger.info(
                "[DETECTOR] layout=%s names=%s",
                "coco" if self._coco_layout else "custom",
                list(names.values())[:12],
            )
        return self._model

    def _class_filter(self):
        """Which class indices to request from the model this call."""
        model = self._model
        if model is None or self._coco_layout:
            return self.class_ids
        names = getattr(model, "names", {}) or {}
        allowed = set(VEHICLE_NAMES)
        if self.include_bicycles:
            allowed.add("bicycle")
        ids = []
        for i, n in names.items():
            mapped = normalize_vehicle_class(n) or str(n).lower()
            if mapped in allowed:
                ids.append(int(i))
        return ids or None

    def warmup(self) -> None:
        """Run one dummy inference so the first real frame isn't slow."""
        model = self._ensure_model()
        dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
        model.predict(dummy, verbose=False, imgsz=self.imgsz, device=self.device)
        logger.info("[DETECTOR] warmup complete")

    def detect(
        self,
        frame: np.ndarray,
        camera_id: Optional[str] = None,
        pts_ms: Optional[float] = None,
    ) -> List[Detection]:
        """Detect vehicles in one BGR frame. Returns [] on model failure."""
        model = self._ensure_model()
        t0 = time.perf_counter()
        try:
            results = model.predict(
                frame,
                verbose=False,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                imgsz=self.imgsz,
                device=self.device,
                classes=self._class_filter(),
            )
        except Exception as exc:
            logger.error("[DETECTOR] inference failed: %s", exc)
            return []
        self.last_inference_ms = (time.perf_counter() - t0) * 1000.0
        self.frames_inferred += 1

        detections: List[Detection] = []
        if not results:
            return detections
        r = results[0]
        if r.boxes is None:
            return detections

        boxes = r.boxes.xyxy.cpu().numpy() if hasattr(r.boxes.xyxy, "cpu") else np.asarray(r.boxes.xyxy)
        confs = r.boxes.conf.cpu().numpy() if hasattr(r.boxes.conf, "cpu") else np.asarray(r.boxes.conf)
        clss = r.boxes.cls.cpu().numpy() if hasattr(r.boxes.cls, "cpu") else np.asarray(r.boxes.cls)
        names = getattr(model, "names", {}) or {}

        for box, conf, cls in zip(boxes, confs, clss):
            cls_id = int(cls)
            raw = names.get(cls_id)
            if raw is None and hasattr(names, "get"):
                raw = names.get(str(cls_id))
            name = normalize_vehicle_class(raw) if raw else None
            if name is None:
                name = VEHICLE_CLASS_IDS.get(cls_id)
            if name is None and cls_id in self.class_ids:
                name = class_name_for(cls_id)
            if name is None:
                continue
            detections.append(
                Detection(
                    bbox=[float(box[0]), float(box[1]), float(box[2]), float(box[3])],
                    class_name=name,
                    confidence=float(conf),
                    camera_id=camera_id,
                    pts_ms=pts_ms,
                    class_id=cls_id,
                )
            )
        return detections
