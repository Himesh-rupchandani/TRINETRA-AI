"""
Vehicle detection with Ultralytics YOLO11 (spec §11, §12).

Design for hackathon hardware:
- yolo11s by default, configurable via MODEL_PATH.
- Vehicle classes only — `classes=` filter is passed to the model so non-vehicle
  predictions are discarded early.
- imgsz configurable; frame skipping is done upstream by the pipeline.
- Torch/ultralytics imports are lazy so the rest of the engine (and its unit
  tests) work without them installed.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from .classes import VEHICLE_CLASS_IDS, class_name_for

logger = logging.getLogger("cv_engine.detection")


@dataclass
class Detection:
    """One detected vehicle in one frame (spec §11 example shape)."""

    bbox: List[float]            # [x1, y1, x2, y2] in frame pixels
    class_name: str              # car | motorcycle | bus | truck
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
        nms_iou: float = 0.45,
    ):
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.imgsz = imgsz
        self.device = device
        # NMS IoU. Left unset here the model used Ultralytics' default 0.7, which
        # leaves two or three boxes on a single vehicle; 0.45 keeps the best one
        # per vehicle. Neighbouring vehicles are unaffected (their mutual IoU is
        # far below 0.45), so no two vehicles are ever merged into one box.
        self.nms_iou = nms_iou
        self.class_ids = sorted(
            list(VEHICLE_CLASS_IDS.keys()) + ([1] if include_bicycles else [])
        )
        self._model = None
        self.last_inference_ms: Optional[float] = None
        self.frames_inferred = 0

    def _ensure_model(self):
        if self._model is None:
            from ultralytics import YOLO  # lazy: heavy import

            logger.info("[DETECTOR] loading YOLO model %s (device=%s)", self.model_path, self.device)
            self._model = YOLO(self.model_path)
        return self._model

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
                iou=self.nms_iou,
                imgsz=self.imgsz,
                device=self.device,
                # Vehicle classes only — never a person/bench/shadow.
                classes=self.class_ids,
                # One vehicle -> one box, even when the model hedges between
                # car / bus / truck for the same vehicle.
                agnostic_nms=True,
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

        frame_h, frame_w = frame.shape[:2]
        for box, conf, cls in zip(boxes, confs, clss):
            cls_id = int(cls)
            name = VEHICLE_CLASS_IDS.get(cls_id)
            if name is None and cls_id in self.class_ids:
                name = class_name_for(cls_id)
            if name is None:
                continue
            # The model's own rectangle, clipped to the frame. Ultralytics has
            # already undone its letterbox/padding internally, so the values in
            # `r.boxes.xyxy` are in this exact array's pixel space: rescaling
            # them again here is the classic way to *create* oversized boxes.
            x1 = max(0.0, min(float(frame_w) - 1.0, float(box[0])))
            y1 = max(0.0, min(float(frame_h) - 1.0, float(box[1])))
            x2 = max(x1 + 1.0, min(float(frame_w), float(box[2])))
            y2 = max(y1 + 1.0, min(float(frame_h), float(box[3])))
            if x2 - x1 < 2.0 or y2 - y1 < 2.0:
                continue
            detections.append(
                Detection(
                    bbox=[x1, y1, x2, y2],
                    class_name=name,
                    confidence=float(conf),
                    camera_id=camera_id,
                    pts_ms=pts_ms,
                    class_id=cls_id,
                )
            )
        return detections
