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

import importlib.util
import logging
import sys
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from .classes import VEHICLE_CLASS_IDS, class_name_for

logger = logging.getLogger("cv_engine.detection")

# A box as the merge step wants it: (x1, y1, x2, y2, class_id, confidence).
Box = Tuple[float, float, float, float, int, float]

# Where the multi-scale geometry lives (the standalone module ships it, and the
# backend keeps the reference copy it was measured against).
_MULTISCALE_PATH = (Path(__file__).resolve().parent.parent.parent
                    / "trinetra_detection" / "core" / "multiscale.py")


@lru_cache(maxsize=1)
def _multiscale():
    """Load the multi-scale geometry helper, or None when it is not present.

    cv-engine, the backend and ``trinetra_detection`` are separate deliverables
    that must each run alone, so this is a by-path import that degrades safely
    instead of a hard dependency: without the file the detector runs its single
    pass, exactly as it always did. Reusing the one implementation - rather than
    pasting a third copy of rules that must agree - is deliberate; the standalone
    suite pins its behaviour with ``tests/test_multiscale.py``.
    """
    if not _MULTISCALE_PATH.is_file():
        logger.info("[DETECTOR] multi-scale geometry not found at %s; single pass only",
                    _MULTISCALE_PATH)
        return None
    try:
        spec = importlib.util.spec_from_file_location("cv_engine_multiscale", str(_MULTISCALE_PATH))
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as exc:  # pragma: no cover - depends on a sibling checkout
        logger.warning("[DETECTOR] multi-scale geometry unavailable (%s); single pass only", exc)
        return None


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
        multiscale: bool = False,
        strips: int = 2,
    ):
        # Multi-scale is OFF by default: this same detector serves the 24/7 ingest
        # pipeline, where CPU is the scarce resource. Live-view callers opt in
        # (settings.live_multiscale) because a person reading boxes on screen is
        # the one place a second look at native resolution pays for itself.
        self.multiscale = bool(multiscale)
        self.strips = max(1, int(strips))
        self.last_passes: list = []
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
        """Detect vehicles in one BGR frame. Returns [] on model failure.

        With ``multiscale`` the frame is seen whole *and* as overlapping
        native-resolution strips, and the sightings are merged into one box per
        vehicle. No rectangle is padded, grown or re-centred by this code: each
        box is the model's own, mapped back through its crop offset and clipped
        to the frame.
        """
        t0 = time.perf_counter()
        helpers = _multiscale() if self.multiscale else None
        try:
            if helpers is None:
                boxes = self._predict(frame, self.imgsz)
                passes = [{"region": "whole", "imgsz": int(self.imgsz), "count": len(boxes)}]
            else:
                boxes, passes = helpers.collect_multiscale(
                    self._predict, frame, self.conf_threshold, self.imgsz,
                    mode="auto", strips=self.strips,
                )
                # One vehicle, one box across the passes. Containment is guarded
                # by relative area here too, so a motorcycle in front of a bus
                # stays two boxes.
                boxes = helpers.suppress_duplicates(boxes, iou_thr=self.nms_iou)
        except Exception as exc:
            logger.error("[DETECTOR] inference failed: %s", exc)
            return []
        self.last_inference_ms = (time.perf_counter() - t0) * 1000.0
        self.last_passes = list(passes)
        self.frames_inferred += 1

        frame_h, frame_w = frame.shape[:2]
        detections: List[Detection] = []
        for x1, y1, x2, y2, cls_id, conf in boxes:
            name = VEHICLE_CLASS_IDS.get(int(cls_id))
            if name is None and int(cls_id) in self.class_ids:
                name = class_name_for(int(cls_id))
            if name is None:
                continue          # a non-vehicle class never becomes a "vehicle"
            # The model's own rectangle, clipped to the frame. Ultralytics has
            # already undone its letterbox/padding internally, so these values are
            # in this array's pixel space: rescaling them again here is the
            # classic way to *create* oversized boxes.
            x1 = max(0.0, min(float(frame_w) - 1.0, float(x1)))
            y1 = max(0.0, min(float(frame_h) - 1.0, float(y1)))
            x2 = max(x1 + 1.0, min(float(frame_w), float(x2)))
            y2 = max(y1 + 1.0, min(float(frame_h), float(y2)))
            if x2 - x1 < 2.0 or y2 - y1 < 2.0:
                continue
            detections.append(
                Detection(
                    bbox=[x1, y1, x2, y2],
                    class_name=name,
                    confidence=float(conf),
                    camera_id=camera_id,
                    pts_ms=pts_ms,
                    class_id=int(cls_id),
                )
            )
        return detections

    def _predict(self, image: np.ndarray, imgsz: int, conf: Optional[float] = None) -> List[Box]:
        """One model call on one array, in that array's own pixel space.

        Returns ``(x1, y1, x2, y2, class_id, confidence)``: the model's boxes,
        clipped to the array it was given. Each crop the multi-scale pass feeds in
        gets its *own* ``imgsz``, so no pixel detail is thrown away - that is the
        whole point of the second look.
        """
        model = self._ensure_model()
        results = model.predict(
            image,
            verbose=False,
            conf=float(self.conf_threshold if conf is None else conf),
            iou=self.nms_iou,
            imgsz=int(imgsz),
            device=self.device,
            classes=self.class_ids,      # vehicle classes only
            agnostic_nms=True,           # one vehicle -> one box
        )
        out: List[Box] = []
        if not results:
            return out
        r = results[0]
        if r.boxes is None:
            return out
        # Read the arrays first, then their size: some callers (and tests) hand
        # back a plain namespace of tensors, which has no __len__ of its own.
        boxes = np.asarray(r.boxes.xyxy.cpu().numpy() if hasattr(r.boxes.xyxy, "cpu")
                           else r.boxes.xyxy).reshape(-1, 4)
        confs = np.asarray(r.boxes.conf.cpu().numpy() if hasattr(r.boxes.conf, "cpu")
                            else r.boxes.conf).reshape(-1)
        clss = np.asarray(r.boxes.cls.cpu().numpy() if hasattr(r.boxes.cls, "cpu")
                           else r.boxes.cls).reshape(-1)
        if boxes.shape[0] == 0:
            return out
        h, w = image.shape[:2]
        for box, conf, cls in zip(boxes, confs, clss):
            x1 = max(0.0, min(float(w) - 1.0, float(box[0])))
            y1 = max(0.0, min(float(h) - 1.0, float(box[1])))
            x2 = max(x1 + 1.0, min(float(w), float(box[2])))
            y2 = max(y1 + 1.0, min(float(h), float(box[3])))
            if x2 - x1 < 2.0 or y2 - y1 < 2.0:
                continue
            out.append((x1, y1, x2, y2, int(cls), float(conf)))
        return out
