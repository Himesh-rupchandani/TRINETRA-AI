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
        """Find the weights: configured path (relative to backend root), the
        in-repo fallback weight, or a bare name for one-time auto-download."""
        configured = (getattr(settings, "YOLO_MODEL_PATH", "") or "yolo11s.pt").strip()
        backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        candidates = [
            configured,
            os.path.join(backend_root, configured),
            # This checkout ships the weight next to the app package (backend root)
            # rather than under models/; without this candidate the configured
            # name silently loses to the smaller fallback weight, and the bigger
            # weight is what keeps boxes on individual vehicles.
            os.path.join(backend_root, os.path.basename(configured)),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        # Offline fallback: the standalone detection module ships the official
        # YOLO11n (COCO) weight in git. Prefer it over a network download so
        # vehicle detection works without internet (e.g. at the venue).
        repo_root = os.path.abspath(os.path.join(backend_root, "..", ".."))
        local_fallback = os.path.join(repo_root, "trinetra_detection", "models", "yolo11n.pt")
        if os.path.isfile(local_fallback):
            logger.info(f"[DETECTION] Using in-repo fallback weights: {local_fallback}")
            return local_fallback
        # Not on disk: fall back to the bare weight name so Ultralytics can
        # fetch the official asset once and cache it.
        return os.path.basename(configured) or "yolo11s.pt"

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
    def detect(
        self,
        frame: np.ndarray,
        conf: Optional[float] = None,
        imgsz: Optional[int] = None,
    ) -> List[VehicleDetection]:
        """Run the detector on one BGR frame and return real vehicle boxes.

        The rectangle returned here IS the model's rectangle, clipped to the
        frame and nothing else: no padding, no growth, no re-centring, no fixed
        size, no hard-coded coordinates. Ultralytics letterboxes the input
        internally and already hands back coordinates mapped to *this* array, so
        applying any extra scale factor here is exactly what would create
        mis-positioned or oversized boxes.

        ``conf`` / ``imgsz`` let the offline video pass ask for different
        settings than the live view (see the ANALYSIS_* settings) without making
        the live loop pay for them.
        """
        model = self._ensure_model()
        if model is None:
            return []
        threshold = float(
            conf if conf is not None else getattr(settings, "CONFIDENCE_THRESHOLD", 0.45)
        )
        size = int(imgsz if imgsz is not None else getattr(settings, "DETECTION_IMGSZ", 640))
        iou = float(getattr(settings, "DETECTION_IOU", 0.45))
        agnostic = bool(getattr(settings, "DETECTION_AGNOSTIC_NMS", True))
        t0 = time.perf_counter()
        try:
            # One inference at a time keeps CPU usage bounded across cameras.
            with self._infer_lock:
                results = model.predict(
                    frame,
                    verbose=False,
                    conf=threshold,
                    iou=iou,
                    imgsz=size,
                    device="cpu",
                    # Only road vehicles are requested, so a person, a bench or
                    # a shadow can never come back as a "vehicle".
                    classes=list(VEHICLE_CLASS_IDS.keys()),
                    # One box per vehicle even when the model hedges between
                    # car/bus/truck for the same one. Suppression is IoU based,
                    # so two separate vehicles stay two separate detections.
                    agnostic_nms=agnostic,
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
        h, w = frame.shape[:2]
        for box, c, k in zip(xyxy, confs, clss):
            name = VEHICLE_CLASS_IDS.get(int(k))
            if name is None or float(c) < threshold:
                continue
            # Clip to the real frame bounds (this only ever *bounds* a box, it
            # never enlarges one) and drop degenerate rectangles.
            x1 = max(0, min(w - 1, int(box[0])))
            y1 = max(0, min(h - 1, int(box[1])))
            x2 = max(x1 + 1, min(w, int(box[2])))
            y2 = max(y1 + 1, min(h, int(box[3])))
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue
            detections.append(
                VehicleDetection(
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    class_name=name, confidence=float(c),
                )
            )
        return detections

    # ---------------------------------------------------------------- drawing
    @staticmethod
    def draw(frame: np.ndarray, detections: List[VehicleDetection]) -> np.ndarray:
        """Draw the model's boxes in green, in place, with OpenCV.

        The box drawn here is exactly ``d.x1..d.y2`` clipped to the frame — the
        rectangle is never grown, padded or replaced by a fixed size. Line width
        and label size follow the frame/box so a distant car does not arrive
        wearing a label bigger than itself.

        ``DETECTION_BOX_FILL_ALPHA > 0`` adds a light tint inside the box only
        (0.0 = outline only). It used to be 0.55, which painted whole road
        sections green whenever a box was even slightly generous.
        """
        fill_alpha = min(
            max(float(getattr(settings, "DETECTION_BOX_FILL_ALPHA", 0.18) or 0.0), 0.0), 1.0
        )
        h, w = frame.shape[:2]
        # 1-3 px: thin on a phone-sized stream, medium on a 1080p wall.
        thickness = max(1, min(3, int(round(min(h, w) / 360.0))))
        # The tint is composited ONCE over the union of all boxes, so a row of
        # neighbouring vehicles (whose boxes touch) does not stack into a green
        # wall — the border is what marks each vehicle.
        if fill_alpha > 0:
            covered = np.zeros((h, w), dtype=bool)
            for d in detections:
                x1, y1 = max(0, d.x1), max(0, d.y1)
                x2, y2 = min(w, d.x2), min(h, d.y2)
                if x2 > x1 and y2 > y1:
                    covered[y1:y2, x1:x2] = True
            if covered.any():
                green = np.full_like(frame, GREEN)
                frame[covered] = (
                    frame[covered] * (1.0 - fill_alpha) + green[covered] * fill_alpha
                ).astype(frame.dtype)

        for d in detections:
            # Clip the box to the frame before touching pixels.
            x1, y1 = max(0, d.x1), max(0, d.y1)
            x2, y2 = min(w, d.x2), min(h, d.y2)
            if x2 <= x1 or y2 <= y1:
                continue
            cv2.rectangle(frame, (x1, y1), (x2, y2), GREEN, thickness)

            # Small label, sized to the box, kept inside the frame.
            label = f"{d.class_name} {d.confidence:.2f}"
            box_h = max(6, y2 - y1)
            font = max(0.32, min(0.55, box_h / 130.0))
            tth = 1 if box_h < 110 else 2
            (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font, tth)
            tag_h = th + baseline + 4
            top = y1 - tag_h if y1 - tag_h >= 0 else min(y1, max(0, h - tag_h))
            left = min(x1, max(0, w - (tw + 8)))
            cv2.rectangle(frame, (left, top), (left + tw + 6, top + tag_h), GREEN, -1)
            cv2.putText(frame, label, (left + 3, top + tag_h - baseline - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, font, (0, 0, 0), tth, cv2.LINE_AA)
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
