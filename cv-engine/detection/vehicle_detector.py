"""
Vehicle detection with Ultralytics YOLO11.

This detector is intentionally restricted to road-vehicle classes and is used
by the PTS-driven tracker in ``tracking.vehicle_tracker``.  It adds conservative
post-NMS de-duplication across optional overlapping tiles, which improves
small/distant CCTV vehicle recall without creating two boxes for the same car
at a tile boundary.

Torch/Ultralytics imports remain lazy so unit tests and non-CV backend work do
not need heavyweight model dependencies installed.
"""
from __future__ import annotations

import math
import logging
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .classes import EXTRA_VEHICLE_CLASS_IDS, VEHICLE_CLASS_IDS, class_name_for

logger = logging.getLogger("cv_engine.detection")


@dataclass
class Detection:
    """One trained-model vehicle detection in source-frame pixel coordinates."""

    bbox: List[float]            # [x1, y1, x2, y2] in frame pixels
    class_name: str              # bicycle | car | motorcycle | bus | truck
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


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)


def _iou(a: Sequence[float], b: Sequence[float]) -> float:
    ax1, ay1, ax2, ay2 = (float(v) for v in a)
    bx1, by1, bx2, by2 = (float(v) for v in b)
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 1e-6 else 0.0


def _intersection_over_smaller(a: Sequence[float], b: Sequence[float]) -> float:
    ax1, ay1, ax2, ay2 = (float(v) for v in a)
    bx1, by1, bx2, by2 = (float(v) for v in b)
    inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    smaller = min(area_a, area_b)
    return inter / smaller if smaller > 1e-6 else 0.0


class VehicleDetector:
    """Lazy, thread-safe YOLO11 vehicle detector with optional tiled recall pass."""

    def __init__(
        self,
        model_path: str = "yolo11n.pt",
        conf_threshold: float = 0.35,
        imgsz: int = 960,
        device: str = "cpu",
        include_bicycles: bool = True,
        nms_iou_threshold: float = 0.70,
        duplicate_iou_threshold: float = 0.82,
        max_detections: int = 300,
        tile_grid: int = 1,
        tile_overlap: float = 0.20,
        tile_min_frame_edge: int = 1400,
    ):
        self.model_path = model_path
        self.conf_threshold = float(conf_threshold)
        self.imgsz = int(imgsz)
        self.device = device
        self.class_ids = sorted(
            list(VEHICLE_CLASS_IDS.keys())
            + (list(EXTRA_VEHICLE_CLASS_IDS.keys()) if include_bicycles else [])
        )
        self.nms_iou_threshold = float(nms_iou_threshold)
        self.duplicate_iou_threshold = float(duplicate_iou_threshold)
        self.max_detections = int(max_detections)
        self.tile_grid = int(tile_grid)
        self.tile_overlap = float(tile_overlap)
        self.tile_min_frame_edge = int(tile_min_frame_edge)
        self._model = None
        self._model_lock = threading.Lock()
        self._infer_lock = threading.Lock()
        self.last_inference_ms: Optional[float] = None
        self.frames_inferred = 0

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is None:
                from ultralytics import YOLO  # lazy: heavy import

                logger.info("[DETECTOR] loading YOLO model %s (device=%s)", self.model_path, self.device)
                self._model = YOLO(self.model_path)
        return self._model

    def _predict_kwargs(self) -> dict:
        return {
            "verbose": False,
            "conf": max(0.01, min(self.conf_threshold, 0.99)),
            "iou": max(0.05, min(self.nms_iou_threshold, 0.99)),
            "imgsz": max(32, self.imgsz),
            "device": self.device,
            "classes": self.class_ids,
            "max_det": max(1, self.max_detections),
            "agnostic_nms": False,
        }

    def warmup(self) -> None:
        """Run one dummy inference so the first live frame is not slow."""
        model = self._ensure_model()
        dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
        with self._infer_lock:
            model.predict(dummy, **self._predict_kwargs())
        logger.info("[DETECTOR] warmup complete")

    def _regions(self, frame: np.ndarray) -> List[Tuple[int, int, np.ndarray]]:
        """Full frame plus an optional overlapping high-resolution tile grid."""
        h, w = frame.shape[:2]
        grid = max(1, self.tile_grid)
        if grid <= 1 or max(h, w) < max(1, self.tile_min_frame_edge):
            return [(0, 0, frame)]
        overlap = max(0.0, min(self.tile_overlap, 0.45))
        divisor = grid - (grid - 1) * overlap
        tile_w = min(w, max(1, int(math.ceil(w / divisor))))
        tile_h = min(h, max(1, int(math.ceil(h / divisor))))
        xs = [int(round(i * (w - tile_w) / (grid - 1))) for i in range(grid)]
        ys = [int(round(i * (h - tile_h) / (grid - 1))) for i in range(grid)]
        regions: List[Tuple[int, int, np.ndarray]] = [(0, 0, frame)]
        for y in ys:
            for x in xs:
                regions.append((x, y, frame[y : y + tile_h, x : x + tile_w]))
        return regions

    def _deduplicate(self, detections: Sequence[Detection]) -> List[Detection]:
        """Suppress only near-identical same-object boxes across model passes."""
        threshold = max(0.50, min(self.duplicate_iou_threshold, 0.99))
        kept: List[Detection] = []
        for candidate in sorted(detections, key=lambda det: det.confidence, reverse=True):
            duplicate = False
            for existing in kept:
                overlap = _iou(candidate.bbox, existing.bbox)
                containment = _intersection_over_smaller(candidate.bbox, existing.bbox)
                same_class = candidate.class_name == existing.class_name
                needed = threshold if same_class else max(0.92, threshold)
                if overlap >= needed or (same_class and containment >= max(0.92, threshold + 0.08)):
                    duplicate = True
                    break
            if not duplicate:
                kept.append(candidate)
        return kept

    def detect(
        self,
        frame: np.ndarray,
        camera_id: Optional[str] = None,
        pts_ms: Optional[float] = None,
    ) -> List[Detection]:
        """Detect all supported visible vehicles in one BGR frame.

        YOLO performs its class-aware NMS first. The conservative second pass
        only joins duplicate predictions caused by overlapping tiles; vehicles
        next to or partly in front of each other remain separate detections.
        """
        if frame is None or getattr(frame, "size", 0) == 0:
            return []
        model = self._ensure_model()
        h, w = frame.shape[:2]
        t0 = time.perf_counter()
        detections: List[Detection] = []
        try:
            with self._infer_lock:
                for offset_x, offset_y, image in self._regions(frame):
                    results = model.predict(image, **self._predict_kwargs())
                    if not results:
                        continue
                    result = results[0]
                    boxes_obj = getattr(result, "boxes", None)
                    if boxes_obj is None:
                        continue
                    boxes = _as_numpy(boxes_obj.xyxy)
                    confs = _as_numpy(boxes_obj.conf).reshape(-1)
                    classes = _as_numpy(boxes_obj.cls).reshape(-1)
                    for box, confidence, class_raw in zip(boxes, confs, classes):
                        try:
                            class_id = int(class_raw)
                            score = float(confidence)
                            x1, y1, x2, y2 = (float(v) for v in box[:4])
                        except (TypeError, ValueError):
                            continue
                        if class_id not in self.class_ids or not math.isfinite(score):
                            continue
                        name = class_name_for(class_id)
                        x1 = min(max(0.0, x1 + offset_x), w - 1.0)
                        y1 = min(max(0.0, y1 + offset_y), h - 1.0)
                        x2 = min(max(0.0, x2 + offset_x), w - 1.0)
                        y2 = min(max(0.0, y2 + offset_y), h - 1.0)
                        if x2 - x1 < 1.0 or y2 - y1 < 1.0:
                            continue
                        detections.append(
                            Detection(
                                bbox=[x1, y1, x2, y2],
                                class_name=name,
                                confidence=score,
                                camera_id=camera_id,
                                pts_ms=pts_ms,
                                class_id=class_id,
                            )
                        )
        except Exception as exc:
            # Some model libraries include paths in their repr; keep logs
            # useful but never make a stream URL/credential observable.
            logger.error("[DETECTOR] inference failed (%s)", type(exc).__name__)
            return []

        self.last_inference_ms = (time.perf_counter() - t0) * 1000.0
        self.frames_inferred += 1
        return self._deduplicate(detections)
