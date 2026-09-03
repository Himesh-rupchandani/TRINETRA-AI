"""YOLO11 vehicle detection.

Single responsibility: frame in, :class:`Detection` list out. Tracking lives in
:mod:`tracking.vehicle_tracker`; the live pipeline runs detection and tracking
in one ultralytics call (see that module) so a frame is never inferred twice.
This class is what probe/benchmark scripts and the unit tests use.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from config.settings import Settings
from detection.classes import COCO_VEHICLE_CLASSES, VEHICLE_CLASS_IDS, Detection
from logging_setup import log_event

log = logging.getLogger("trinetra.detect")


def resolve_device(requested: str = "auto") -> str:
    """'auto' -> 'cuda' when a GPU is visible, else 'cpu'."""
    if requested and requested != "auto":
        return requested
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001 - torch missing entirely
        return "cpu"


def resolve_model_path(model_path: str) -> str:
    """Accept a bare weight name, a path, or a packaged ``.pt``/``.yaml``.

    ``yolo11n.pt`` is resolved against ``./models`` first so an offline machine
    does not attempt a download it cannot complete.
    """
    candidate = Path(model_path)
    if candidate.is_file():
        return str(candidate)
    local = Path(__file__).resolve().parents[1] / "models" / candidate.name
    if local.is_file():
        return str(local)
    return model_path  # let ultralytics try its own download


class VehicleDetector:
    """Thin, testable wrapper around an ultralytics YOLO11 model."""

    def __init__(
        self,
        settings: Settings,
        model=None,
        class_ids: Sequence[int] = VEHICLE_CLASS_IDS,
    ) -> None:
        self.settings = settings
        self.class_ids = tuple(int(c) for c in class_ids)
        self.device = resolve_device(settings.device)
        self._model = model
        self._model_path = resolve_model_path(settings.model_path)
        self.inference_ms_total = 0.0
        self.inference_count = 0
        self.detections_total = 0

    # -- model --------------------------------------------------------------
    @property
    def model(self):
        """Lazily load weights: importing this module must stay cheap."""
        if self._model is None:
            started = time.perf_counter()
            from ultralytics import YOLO

            self._model = YOLO(self._model_path)
            log_event(
                log,
                "model_loaded",
                model=self._model_path,
                device=self.device,
                load_ms=(time.perf_counter() - started) * 1000,
            )
        return self._model

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    # -- inference ----------------------------------------------------------
    def predict_kwargs(self, **overrides) -> dict:
        kwargs = dict(
            conf=self.settings.conf_threshold,
            iou=self.settings.iou_threshold,
            imgsz=self.settings.imgsz,
            device=self.device,
            classes=list(self.class_ids),
            verbose=False,
        )
        kwargs.update(overrides)
        return kwargs

    def detect(
        self,
        frame: np.ndarray,
        camera_id: str,
        pts_ms: float,
        continuous_ms: float = 0.0,
    ) -> list[Detection]:
        """Run one inference and return vehicle detections for ``frame``."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return []
        started = time.perf_counter()
        results = self.model.predict(frame, **self.predict_kwargs())
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.inference_ms_total += elapsed_ms
        self.inference_count += 1

        detections = self._parse(results[0] if results else None, camera_id, pts_ms, continuous_ms)
        self.detections_total += len(detections)
        if detections:
            log_event(
                log,
                "vehicle_detected",
                level=logging.DEBUG,
                camera=camera_id,
                count=len(detections),
                inference_ms=elapsed_ms,
                pts_ms=pts_ms,
                top_class=detections[0].class_name,
                top_conf=round(detections[0].confidence, 3),
            )
        return detections

    def _parse(self, result, camera_id: str, pts_ms: float, continuous_ms: float) -> list[Detection]:
        """Convert an ultralytics Result into our Detection objects."""
        if result is None or getattr(result, "boxes", None) is None:
            return []
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return []
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        classes = boxes.cls.cpu().numpy().astype(int)
        names = getattr(result, "names", COCO_VEHICLE_CLASSES) or {}

        detections: list[Detection] = []
        for box, conf, cls in zip(xyxy, confs, classes):
            if int(cls) not in COCO_VEHICLE_CLASSES:
                continue
            if float(conf) < self.settings.conf_threshold:
                continue
            detections.append(
                Detection(
                    bbox=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                    class_name=str(names.get(int(cls), COCO_VEHICLE_CLASSES[int(cls)])),
                    confidence=float(conf),
                    camera_id=camera_id,
                    pts_ms=float(pts_ms),
                    continuous_ms=float(continuous_ms),
                    class_id=int(cls),
                )
            )
        detections.sort(key=lambda d: d.confidence, reverse=True)
        limit = self.settings.max_detections
        return detections[:limit] if limit else detections

    # -- metrics ------------------------------------------------------------
    @property
    def avg_inference_ms(self) -> float:
        return self.inference_ms_total / self.inference_count if self.inference_count else 0.0


class InferenceGate:
    """Decides *whether* a decoded frame should be inferred on.

    Decoding a 25 fps government feed and inferring on every frame is how a
    hackathon laptop dies. Two independent throttles, both off by default:

    * ``frame_skip`` — infer on 1 of every N+1 decoded frames.
    * ``inference_interval_s`` — never infer faster than this, whatever the
      decode rate (this is the one that keeps latency bounded when a feed
      suddenly delivers 50 fps).
    """

    def __init__(self, frame_skip: int = 0, min_interval_s: float = 0.0) -> None:
        self.frame_skip = max(int(frame_skip), 0)
        self.min_interval_s = max(float(min_interval_s), 0.0)
        self._since_last = 0
        self._last_infer_monotonic: Optional[float] = None
        self.frames_seen = 0
        self.frames_inferred = 0

    def should_infer(self, now_monotonic: float | None = None) -> bool:
        self.frames_seen += 1
        if self.frame_skip and self._since_last < self.frame_skip:
            self._since_last += 1
            return False
        if self.min_interval_s and self._last_infer_monotonic is not None:
            now = now_monotonic if now_monotonic is not None else time.monotonic()
            if (now - self._last_infer_monotonic) < self.min_interval_s:
                return False
        self._since_last = 0
        self.frames_inferred += 1
        self._last_infer_monotonic = (
            now_monotonic if now_monotonic is not None else time.monotonic()
        )
        return True

    @property
    def inference_ratio(self) -> float:
        return self.frames_inferred / self.frames_seen if self.frames_seen else 0.0
