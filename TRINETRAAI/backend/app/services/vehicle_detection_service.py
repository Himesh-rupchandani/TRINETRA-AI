"""
Real-time vehicle detection service (OpenCV + YOLO11).

Adds green bounding boxes around vehicles on the live camera frames that the
backend already serves through ``CameraManager.generate_mjpeg_stream``.

Design (performance-first, for a live CCTV system):
- The detection model is loaded ONCE, lazily, and shared by every camera
  stream (thread-safe). Weights are never reloaded per frame.
- Inference runs at most every ``DETECTION_EVERY_N_FRAMES`` frames per camera;
  the last real detections are re-drawn on the frames in between, so boxes
  are always model-generated, never fabricated.
- Only COCO vehicle classes are requested from the model (car, motorcycle,
  bus, truck) and detections under ``CONFIDENCE_THRESHOLD`` are discarded.
- ``ultralytics`` / torch are imported lazily: when they are missing, or the
  weights cannot be found, the service disables itself and the live view
  keeps working exactly as before (no boxes).
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import cv2
import numpy as np

from ..core.config import settings
from ..core.logging_config import logger

# COCO class id -> label, restricted to road vehicles.
VEHICLE_CLASS_IDS: Dict[int, str] = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
GREEN = (0, 255, 0)  # BGR


@dataclass
class VehicleDetection:
    """One vehicle detected by the model in one frame (pixel coordinates)."""

    x1: int
    y1: int
    x2: int
    y2: int
    class_name: str
    confidence: float


class VehicleDetectionService:
    """Singleton wrapper around a YOLO11 vehicle detector with per-camera throttling."""

    def __init__(self) -> None:
        self._model = None
        self._model_lock = threading.Lock()
        self._infer_lock = threading.Lock()
        self._disabled_reason: Optional[str] = None
        self._state_lock = threading.Lock()
        # camera_id -> (frame counter, last detections, last inference ms)
        self._frame_counter: Dict[str, int] = {}
        self._last_detections: Dict[str, List[VehicleDetection]] = {}
        self.last_inference_ms: Optional[float] = None

    # ------------------------------------------------------------------ model
    @property
    def enabled(self) -> bool:
        return bool(getattr(settings, "VEHICLE_DETECTION_ENABLED", True)) and self._disabled_reason is None

    def _resolve_model_path(self) -> str:
        """Find the weights: configured path (relative to backend root) or bare name (auto-download)."""
        configured = (getattr(settings, "YOLO_MODEL_PATH", "") or "yolo11n.pt").strip()
        candidates = [configured]
        backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        candidates.append(os.path.join(backend_root, configured))
        for c in candidates:
            if os.path.isfile(c):
                return c
        # Not on disk: fall back to the bare weight name so Ultralytics can
        # fetch the official asset once and cache it.
        return os.path.basename(configured) or "yolo11n.pt"

    def _ensure_model(self):
        if self._model is not None or self._disabled_reason is not None:
            return self._model
        with self._model_lock:
            if self._model is not None or self._disabled_reason is not None:
                return self._model
            try:
                from ultralytics import YOLO  # lazy: heavy import

                path = self._resolve_model_path()
                logger.info(f"[DETECTION] Loading vehicle detection model once: {path}")
                t0 = time.perf_counter()
                model = YOLO(path)
                imgsz = int(getattr(settings, "DETECTION_IMGSZ", 640))
                # Warm-up so the first real frame is not slow.
                model.predict(
                    np.zeros((imgsz, imgsz, 3), dtype=np.uint8),
                    verbose=False, imgsz=imgsz, device="cpu",
                )
                self._model = model
                logger.info(f"[DETECTION] Model ready in {time.perf_counter() - t0:.1f}s")
            except Exception as exc:  # missing ultralytics/torch, no weights, no network…
                self._disabled_reason = str(exc)
                logger.warning(
                    f"[DETECTION] Vehicle detection disabled — live view continues without boxes: {exc}"
                )
        return self._model

    # -------------------------------------------------------------- inference
    def detect(self, frame: np.ndarray) -> List[VehicleDetection]:
        """Run the detector on one BGR frame and return real vehicle boxes."""
        model = self._ensure_model()
        if model is None:
            return []
        conf = float(getattr(settings, "CONFIDENCE_THRESHOLD", 0.45))
        imgsz = int(getattr(settings, "DETECTION_IMGSZ", 640))
        t0 = time.perf_counter()
        try:
            # One inference at a time keeps CPU usage bounded across cameras.
            with self._infer_lock:
                results = model.predict(
                    frame,
                    verbose=False,
                    conf=conf,
                    imgsz=imgsz,
                    device="cpu",
                    classes=list(VEHICLE_CLASS_IDS.keys()),
                )
        except Exception as exc:
            logger.error(f"[DETECTION] Inference failed: {exc}")
            return []
        self.last_inference_ms = (time.perf_counter() - t0) * 1000.0

        detections: List[VehicleDetection] = []
        if not results or results[0].boxes is None:
            return detections
        boxes = results[0].boxes
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        clss = boxes.cls.cpu().numpy()
        for box, c, k in zip(xyxy, confs, clss):
            name = VEHICLE_CLASS_IDS.get(int(k))
            if name is None or float(c) < conf:
                continue
            detections.append(
                VehicleDetection(
                    x1=int(box[0]), y1=int(box[1]), x2=int(box[2]), y2=int(box[3]),
                    class_name=name, confidence=float(c),
                )
            )
        return detections

    # ---------------------------------------------------------------- drawing
    @staticmethod
    def draw(frame: np.ndarray, detections: List[VehicleDetection]) -> np.ndarray:
        """Draw green boxes + class/confidence labels in place with OpenCV."""
        for d in detections:
            cv2.rectangle(frame, (d.x1, d.y1), (d.x2, d.y2), GREEN, 2)
            label = f"{d.class_name} {d.confidence:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            ty = d.y1 - 6 if d.y1 - th - 8 > 0 else d.y1 + th + 6
            cv2.rectangle(frame, (d.x1, ty - th - 4), (d.x1 + tw + 6, ty + 4), GREEN, -1)
            cv2.putText(frame, label, (d.x1 + 3, ty), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0, 0, 0), 1, cv2.LINE_AA)
        return frame

    # --------------------------------------------------------------- pipeline
    def annotate(self, camera_id: str, frame: np.ndarray) -> np.ndarray:
        """Detect (throttled per camera) and draw green boxes on a live frame.

        Frames between inference runs re-use the latest real detections so the
        overlay stays stable at full stream rate. Never raises: any failure
        returns the frame unchanged so the live view is never interrupted.
        """
        if not self.enabled or frame is None or frame.size == 0:
            return frame
        every_n = max(1, int(getattr(settings, "DETECTION_EVERY_N_FRAMES", 2)))
        with self._state_lock:
            n = self._frame_counter.get(camera_id, 0)
            self._frame_counter[camera_id] = n + 1
            cached = self._last_detections.get(camera_id, [])
        if n % every_n == 0:
            detections = self.detect(frame)
            with self._state_lock:
                self._last_detections[camera_id] = detections
        else:
            detections = cached
        return self.draw(frame, detections)

    def forget(self, camera_id: str) -> None:
        """Drop cached state for a camera whose live view has ended."""
        with self._state_lock:
            self._frame_counter.pop(camera_id, None)
            self._last_detections.pop(camera_id, None)


# Global singleton — the model is loaded once per backend process.
vehicle_detection_service = VehicleDetectionService()
