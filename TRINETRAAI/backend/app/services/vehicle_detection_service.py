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
from .detection_core import (
    collect_multiscale,
    suppress_duplicates,
)

# COCO class id -> label, restricted to road vehicles.
VEHICLE_CLASS_IDS: Dict[int, str] = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
GREEN = (0, 255, 0)  # BGR

# Ladder the live auto-pacing governor walks (see LIVE_ADAPTIVE_IMGSZ). Sizes
# only ever change the model's INPUT resolution; the returned rectangles are
# still whatever the model measured, so a lower rung means fewer small distant
# vehicles, never a bigger or repositioned box.
IMGSZ_LADDER = (1280, 960, 768, 640, 512)


@dataclass
class VehicleDetection:
    """One vehicle detected by the model in one frame (pixel coordinates)."""

    x1: int
    y1: int
    x2: int
    y2: int
    class_name: str
    confidence: float


def _stale_window_ms(cost_ms: float) -> float:
    """Age after which live boxes are dropped rather than drawn.

    ``LIVE_BOX_MAX_AGE_MS`` is the floor; it widens to two passes of the
    detector's measured cadence so a deliberately deep look (LIVE_QUALITY=max on
    a weak CPU costs ~900 ms a pass here) does not make the overlay flicker, and
    stops widening at ``LIVE_STALENESS_CEILING_MS`` so a detector that has really
    stopped loses its boxes instead of painting a vehicle onto an empty road.
    ``0`` means "never age" - the boxes then stay until replaced.
    """
    floor = float(getattr(settings, "LIVE_BOX_MAX_AGE_MS", 900.0))
    if floor <= 0:
        return 0.0
    ceiling = max(floor, float(getattr(settings, "LIVE_STALENESS_CEILING_MS", 2500.0)))
    return min(max(floor, 2.0 * float(cost_ms or 0.0)), ceiling)


class _LiveView:
    """One camera's background detection worker.

    Exactly one frame may be in flight: the stream hands over a copy when the
    worker is idle and otherwise keeps showing the last real result, so the
    model is never queued up behind itself and a stalled detector cannot eat
    memory. Results are discarded once older than ``LIVE_BOX_MAX_AGE_MS`` so a
    camera that stops producing frames does not keep a vehicle boxed forever.
    """

    def __init__(self, service: "VehicleDetectionService", camera_id: str) -> None:
        self._svc = service
        self._camera_id = camera_id
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._pending = None                # (frame,) waiting to be looked at
        self._busy = False
        self._result: List[VehicleDetection] = []
        self._result_at = 0.0
        self._thread = threading.Thread(target=self._run, name=f"live-detect-{camera_id}", daemon=True)
        self._thread.start()

    # ---------------------------------------------------------------- worker
    def _run(self) -> None:
        while not self._stop.is_set():
            # Long timeout: the Event wakes us the moment a frame is queued, so
            # an idle worker must cost nothing. clear() is what makes the wait
            # mean something - Event.wait() does not consume the flag, and
            # without it this loop would spin at full speed forever.
            self._wake.wait(0.5)
            self._wake.clear()
            if self._stop.is_set():
                break
            with self._lock:
                frame, self._pending = self._pending, None
                if frame is None:
                    continue
            more = False
            try:
                dets = self._svc.detect(frame)
            except Exception as exc:          # a bad frame must not kill the worker
                logger.warning(f"[DETECTION] live pass failed for {self._camera_id}: {exc}")
                dets = None
            # _busy is cleared on BOTH paths: a raised pass that left it set would
            # stop this camera ever queueing another frame, and the viewer would
            # keep seeing one frozen set of boxes with nothing to say so.
            with self._lock:
                self._busy = False
                if dets is not None:
                    self._result = dets
                    self._result_at = time.monotonic() * 1000.0
                more = self._pending is not None
            if more:
                self._wake.set()

    # ------------------------------------------------------------------- api
    def frames(self, frame: np.ndarray) -> List[VehicleDetection]:
        """Boxes to draw on this frame, and queue the frame for the next pass.

        The first frame of a view is measured synchronously - otherwise a viewer
        stares at an unboxed feed for a whole inference before anything appears -
        and once one look is in flight later frames never pile up behind it.
        """
        max_age = self._stale_after_ms()
        with self._lock:
            have = bool(self._result)
            age = time.monotonic() * 1000.0 - self._result_at
            fresh = list(self._result) if (have and (age <= max_age or max_age <= 0)) else []
            if have and not self._busy and not self._stop.is_set():
                self._pending = frame.copy()
                self._busy = True
                self._wake.set()
        if fresh or have:
            return fresh
        try:
            dets = self._svc.detect(frame)
        except Exception:
            return []
        with self._lock:
            self._result = dets
            self._result_at = time.monotonic() * 1000.0
        return list(dets)

    def _stale_after_ms(self) -> float:
        """How old this view's result may be before it is dropped, not drawn."""
        return _stale_window_ms(float(getattr(self._svc, "last_inference_ms", 0.0) or 0.0))

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()


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
        self._last_detections_at: Dict[str, float] = {}
        self._quality_warned = False
        self.last_inference_ms: Optional[float] = None
        # what produced the last result: [{"region": ..., "imgsz": ..., "count": n}]
        self.last_passes: List[dict] = []
        # Live auto-pacing state: the quality level currently in force and the
        # recent inference times it is judged on.
        self._live_level: Optional[tuple] = None
        self._infer_ms_samples: List[float] = []
        # camera_id -> _LiveView (background inference worker for that stream)
        self._live_views: Dict[str, "_LiveView"] = {}

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
                imgsz = int(getattr(settings, "DETECTION_IMGSZ", 960))
                # Warm-up so the first real frame is not slow.
                model.predict(
                    np.zeros((imgsz, imgsz, 3), dtype=np.uint8),
                    verbose=False, imgsz=imgsz, device="cpu",
                )
                self._model = model
                logger.info(
                    f"[DETECTION] Model ready in {time.perf_counter() - t0:.1f}s | live view runs "
                    f"conf={float(getattr(settings, 'CONFIDENCE_THRESHOLD', 0.35)):.2f} "
                    f"imgsz={imgsz} iou={float(getattr(settings, 'DETECTION_IOU', 0.45)):.2f} "
                    f"agnostic_nms={bool(getattr(settings, 'DETECTION_AGNOSTIC_NMS', True))}"
                    + (" (auto-pacing on)" if bool(getattr(settings, "LIVE_ADAPTIVE_IMGSZ", True)) else "")
                )
            except Exception as exc:  # missing ultralytics/torch, no weights, no network…
                self._disabled_reason = str(exc)
                logger.warning(
                    f"[DETECTION] Vehicle detection disabled — live view continues without boxes: {exc}"
                )
        return self._model

    # ------------------------------------------- live quality ladder + pacing
    # Quality levels ordered from cheapest to best, each with the cost of that
    # level relative to a single 768 pass (measured on 1280x720 CPU frames with
    # the shipped weight: 512=103ms, 640=149, 768=207, 960=322, 1280=540,
    # 768+2 native strips=665). The governor measures one level and uses it to
    # place the whole ladder, so a strong machine gets multi-scale live detection
    # and a weak one gets a single pass - automatically, same box geometry.
    QUALITY_LADDER = (
        (512, "single", 0.50),
        (640, "single", 0.72),
        (768, "single", 1.00),
        (960, "single", 1.55),
        (1280, "single", 2.60),
        (768, "strips", 3.20),
        (960, "strips", 3.90),
    )

    def _levels(self) -> List[tuple]:
        """Ladder rungs allowed by the configuration, cheapest first."""
        target = int(getattr(settings, "DETECTION_IMGSZ", 960))
        floor = int(getattr(settings, "LIVE_IMGSZ_FLOOR", 640))
        quality = self._quality_locked()
        allow_multiscale = quality in ("auto", "max") and bool(
            getattr(settings, "LIVE_ADAPTIVE_IMGSZ", True)
        )
        out = [
            (size, mode, cost)
            for (size, mode, cost) in self.QUALITY_LADDER
            if floor <= size <= max(target, floor) and (allow_multiscale or mode == "single")
        ]
        if not out:
            out = [(target, "single", 1.0)]
        if quality == "eco":
            out = [lv for lv in out if lv[1] == "single"] or out
        return out

    def _quality_locked(self) -> str:
        """LIVE_QUALITY, validated once. Unknown values would silently pick a
        quality level, so say which one is actually in force."""
        raw = str(getattr(settings, "LIVE_QUALITY", "auto") or "auto").lower()
        if raw not in ("auto", "eco", "max"):
            if not self._quality_warned:
                self._quality_warned = True
                logger.warning(
                    f"[DETECTION] Unknown LIVE_QUALITY={raw!r}; using 'auto'. "
                    "Valid values are auto | eco | max."
                )
            return "auto"
        return raw

    def _active_locked(self) -> tuple:
        """The level currently in force (imgsz, mode, relative cost)."""
        if self._live_level is not None:
            return self._live_level
        levels = self._levels()
        quality = self._quality_locked()
        target = int(getattr(settings, "DETECTION_IMGSZ", 960))
        if quality == "max":
            return levels[-1]
        # otherwise start at the configured imgsz's single pass, if present
        for lv in levels:
            if lv[0] == target and lv[1] == "single":
                return lv
        return min(levels, key=lambda lv: abs(lv[0] - target))

    def live_imgsz(self) -> int:
        """The inference resolution the live view is currently using."""
        with self._state_lock:
            return self._active_locked()[0]

    def live_mode(self) -> str:
        """``single`` or ``strips``: is the live view looking twice or once?"""
        with self._state_lock:
            return self._active_locked()[1]

    def _pace(self, elapsed_ms: float) -> None:
        """Feed one live measurement into the governor and re-pick the level.

        Two rules make this safe to leave switched on:

        * the estimate comes from the *median* of the last few inferences, so one
          slow frame (another process grabbing the CPU) cannot make the overlay
          flicker between sizes;
        * an upgrade needs headroom (60% of the budget), a downgrade only needs
          the budget to be broken - so the loop settles instead of oscillating.

        Pacing changes how *much* of the frame the model is shown, never what it
        said: no box is resized, moved or invented here.
        """
        quality = self._quality_locked()
        adaptive = bool(getattr(settings, "LIVE_ADAPTIVE_IMGSZ", True))
        budget = float(getattr(settings, "LIVE_INFER_BUDGET_MS", 450.0) or 0.0)
        if not adaptive or quality == "max" or budget <= 0:
            with self._state_lock:
                self._live_level = None
                self._infer_ms_samples = []
            return
        with self._state_lock:
            self._infer_ms_samples = (self._infer_ms_samples + [float(elapsed_ms)])[-5:]
            if len(self._infer_ms_samples) < 3:
                return
            ordered = sorted(self._infer_ms_samples)
            median = ordered[len(ordered) // 2]
            levels = self._levels()
            cur = self._active_locked()
            idx = next((i for i, lv in enumerate(levels) if lv == cur),
                       min(range(len(levels)), key=lambda i: abs(levels[i][0] - cur[0])))
            unit = max(1.0, median) / max(0.05, levels[idx][2])
            target_idx = idx
            if unit * levels[idx][2] > budget:
                affordable = [i for i, lv in enumerate(levels) if unit * lv[2] <= budget]
                target_idx = max(affordable) if affordable else 0
            elif idx + 1 < len(levels) and unit * levels[idx + 1][2] <= 0.6 * budget:
                target_idx = idx + 1
            if target_idx == idx:
                return
            self._live_level = levels[target_idx]
            self._infer_ms_samples = []
            new = levels[target_idx]
        logger.info(
            f"[DETECTION] Live auto-pacing: {cur[1]}@{cur[0]} -> {new[1]}@{new[0]} "
            f"(median {median:.0f} ms, budget {budget:.0f} ms)"
        )

    def reset_pacing(self) -> None:
        """Forget the learned pace (used when settings change or on restart)."""
        with self._state_lock:
            self._live_level = None
            self._infer_ms_samples = []

    # -------------------------------------------------------------- inference
    def _predict_raw(self, model, image, conf: float, size: int, iou: float,
                     agnostic: bool) -> List[tuple]:
        """One model call, returned as ``(x1, y1, x2, y2, class_id, score)``.

        Caller must hold ``_infer_lock``: a multi-scale look at one frame should
        not interleave with another camera's.
        """
        results = model.predict(
            image,
            verbose=False,
            conf=conf,
            iou=iou,
            imgsz=size,
            device="cpu",
            # Only road vehicles are requested, so a person, a bench or a
            # shadow cannot come back as a "vehicle" in the first place.
            classes=list(VEHICLE_CLASS_IDS.keys()),
            # One box per vehicle even when the model hedges between car/bus/
            # truck for the same one. Suppression is IoU based, so two separate
            # vehicles stay two separate detections.
            agnostic_nms=agnostic,
        )
        if not results or results[0].boxes is None:
            return []
        boxes = results[0].boxes
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        clss = boxes.cls.cpu().numpy()
        return [
            (float(b[0]), float(b[1]), float(b[2]), float(b[3]), int(k), float(c))
            for b, c, k in zip(xyxy, confs, clss)
        ]

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

        What this method adds is a *pixel budget*, not a geometry opinion: the
        frame is looked at once whole and (when enabled) again as overlapping
        native-resolution strips, and the resulting boxes are reduced to one per
        vehicle. A car that is 14 px tall at imgsz 640 cannot be boxed tightly
        by any amount of post-processing; seen at native resolution it can,
        which is why multi-scale raises both recall AND tightness.

        ``conf`` / ``imgsz`` let the offline video pass ask for different
        settings than the live view (see the ANALYSIS_* settings). Left ``None``
        - i.e. called from the live stream - the settings defaults apply, the
        quality level comes from the pacing governor, and the measured cost is
        fed back to it.
        """
        model = self._ensure_model()
        if model is None:
            return []
        live = imgsz is None and conf is None
        threshold = float(
            conf if conf is not None else getattr(settings, "CONFIDENCE_THRESHOLD", 0.35)
        )
        if live:
            with self._state_lock:
                size, mode = self._active_locked()[:2]
        else:
            size = int(imgsz if imgsz is not None else getattr(settings, "DETECTION_IMGSZ", 960))
            mode = ("auto" if bool(getattr(settings, "ANALYSIS_MULTISCALE", True)) else "single")
        iou = float(getattr(settings, "DETECTION_IOU", 0.45))
        agnostic = bool(getattr(settings, "DETECTION_AGNOSTIC_NMS", True))
        t0 = time.perf_counter()
        try:
            def _run(image, imgsz_, conf_):
                return self._predict_raw(model, image, conf_, imgsz_, iou, agnostic)

            # One inference at a time keeps CPU usage bounded across cameras.
            with self._infer_lock:
                raw, passes = collect_multiscale(
                    _run,
                    frame,
                    conf=threshold,
                    imgsz=size,
                    mode=mode,
                    strips=int(getattr(settings, "DETECTION_STRIPS", 2)),
                    tile=int(getattr(settings, "DETECTION_TILE", 640)),
                    max_tiles=int(getattr(settings, "DETECTION_MAX_TILES", 6)),
                )
        except Exception as exc:
            logger.error(f"[DETECTION] Inference failed: {exc}")
            return []
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.last_inference_ms = elapsed_ms
        self.last_passes = passes
        if live:
            # Only the live loop re-paces itself; a batch analysis job must not
            # drag the live view's quality level around with its own timings.
            self._pace(elapsed_ms)

        # One box per vehicle: model NMS is per class and IoU based, so a
        # crop-clipped repeat of the same car (IoU ~0.35) survives it. Choosing
        # between duplicates is all this does - it never edits a rectangle.
        kept = suppress_duplicates(
            raw,
            iou_thr=iou,
            containment_thr=float(getattr(settings, "DETECTION_CONTAINMENT_THR", 0.60)),
            containment_area_guard=float(getattr(settings, "DETECTION_CONTAINMENT_AREA_GUARD", 3.0)),
        )

        detections: List[VehicleDetection] = []
        h, w = frame.shape[:2]
        for x1, y1, x2, y2, k, c in kept:
            name = VEHICLE_CLASS_IDS.get(int(k))
            if name is None or float(c) < threshold:
                continue
            # Clip to the real frame bounds (this only ever *bounds* a box, it
            # never enlarges one) and drop degenerate rectangles.
            ix1 = max(0, min(w - 1, int(x1)))
            iy1 = max(0, min(h - 1, int(y1)))
            ix2 = max(ix1 + 1, min(w, int(x2)))
            iy2 = max(iy1 + 1, min(h, int(y2)))
            if ix2 - ix1 < 2 or iy2 - iy1 < 2:
                continue
            detections.append(
                VehicleDetection(
                    x1=ix1, y1=iy1, x2=ix2, y2=iy2,
                    class_name=name, confidence=float(c),
                )
            )
        return detections

    # ---------------------------------------------------------------- drawing
    @staticmethod
    def draw(
        frame: np.ndarray,
        detections: List[VehicleDetection],
        fill_alpha: Optional[float] = None,
    ) -> np.ndarray:
        """Draw the model's boxes in green, in place, with OpenCV.

        The box drawn here is exactly ``d.x1..d.y2`` clipped to the frame — the
        rectangle is never grown, padded or replaced by a fixed size. Line width
        and label size follow the frame/box so a distant car does not arrive
        wearing a label bigger than itself.

        The default is outline only - the border marks the vehicle boundary, which
        is what the reference imagery asks for. ``DETECTION_BOX_FILL_ALPHA`` (or the
        ``fill_alpha`` argument) adds a tint inside the box; it used to be 0.55,
        which painted whole road sections green whenever a box was even slightly
        generous, and a tint is a bad way to make a loose box look intentional.
        """
        if fill_alpha is None:
            fill_alpha = float(getattr(settings, "DETECTION_BOX_FILL_ALPHA", 0.0) or 0.0)
        fill_alpha = min(max(float(fill_alpha), 0.0), 1.0)
        h, w = frame.shape[:2]
        # 1-3 px: thin on a phone-sized stream, medium on a 1080p wall.
        thickness = max(1, min(3, int(round(min(h, w) / 360.0))))
        # The tint is composited ONCE over the union of all boxes, so a row of
        # neighbouring vehicles (whose boxes touch) does not stack into a green
        # wall — the border is what marks each vehicle.
        if fill_alpha:
            covered = np.zeros((h, w), dtype=bool)
            boxes = []
            for d in detections:
                x1, y1 = max(0, d.x1), max(0, d.y1)
                x2, y2 = min(w, d.x2), min(h, d.y2)
                if x2 > x1 and y2 > y1:
                    covered[y1:y2, x1:x2] = True
                    boxes.append((x1, y1, x2, y2))
            if boxes:
                # Work inside the union's bounding box only: on a 1080p live
                # frame this is a fraction of the pixels and avoids allocating a
                # second full-size frame every single stream tick.
                ux1 = min(b[0] for b in boxes); uy1 = min(b[1] for b in boxes)
                ux2 = max(b[2] for b in boxes); uy2 = max(b[3] for b in boxes)
                patch = frame[uy1:uy2, ux1:ux2]
                mask = covered[uy1:uy2, ux1:ux2]
                tint = np.array(GREEN, dtype=frame.dtype)
                patch[mask] = (
                    patch[mask] * (1.0 - fill_alpha) + tint * fill_alpha
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
    def _live_view(self, camera_id: str) -> "_LiveView":
        key = (camera_id or "").lower()
        with self._state_lock:
            view = self._live_views.get(key)
            if view is None:
                view = _LiveView(self, key)
                self._live_views[key] = view
            return view

    def annotate(self, camera_id: str, frame: np.ndarray) -> np.ndarray:
        """Draw the current vehicle boxes on a live frame, without ever slowing
        the stream down to the speed of the model.

        Inference runs on a background worker per camera (``LIVE_ASYNC_DETECT``):
        the stream renders the freshest real detections at its own frame rate,
        and a frame is only handed to the worker when the previous look has
        finished, so CPU - not the MJPEG loop - sets how deep the detector looks.
        That is what makes the multi-scale pass affordable on a live view: it
        buys boxes, and spends detection latency, which is bounded by
        ``LIVE_BOX_MAX_AGE_MS``. Boxes older than that are dropped rather than
        shown at the wrong place, and nothing is ever extrapolated: a box you see
        is a box the model measured on some real frame of this stream.

        With ``LIVE_ASYNC_DETECT=false`` the previous synchronous behaviour is
        used: detect every Nth frame and replay those boxes in between.

        Never raises - a failure returns the frame unchanged, because an
        overlay must never be able to kill somebody's camera view.
        """
        if not self.enabled or frame is None or frame.size == 0:
            return frame
        if not bool(getattr(settings, "LIVE_ASYNC_DETECT", True)):
            return self._annotate_sync(camera_id, frame)
        try:
            view = self._live_view(camera_id)
            return self.draw(frame, view.frames(frame))
        except Exception as exc:
            logger.warning(f"[DETECTION] Live overlay skipped: {exc}")
            return frame

    def _annotate_sync(self, camera_id: str, frame: np.ndarray) -> np.ndarray:
        """Synchronous fallback: model every Nth frame, replay in between."""
        every_n = max(1, int(getattr(settings, "DETECTION_EVERY_N_FRAMES", 2)))
        with self._state_lock:
            n = self._frame_counter.get(camera_id, 0)
            self._frame_counter[camera_id] = n + 1
            cached = self._last_detections.get(camera_id, [])
        if n % every_n == 0:
            detections = self.detect(frame)
            with self._state_lock:
                self._last_detections[camera_id] = detections
                self._last_detections_at[camera_id] = time.monotonic() * 1000.0
            cached = detections
        else:
            # Same rule the async worker uses: a replay that has gone stale is not
            # information any more, it is a box where a vehicle used to be.
            window = _stale_window_ms(float(self.last_inference_ms or 0.0))
            if window > 0:
                with self._state_lock:
                    then = self._last_detections_at.get(camera_id, 0.0)
                if time.monotonic() * 1000.0 - then > window:
                    cached = []
        return self.draw(frame, cached)

    def forget(self, camera_id: str) -> None:
        """Drop cached state for a camera whose live view has ended.

        Called from the MJPEG generator's finally block, so this is also what
        stops a per-camera worker thread from outliving its viewers. The worker
        is stopped OUTSIDE the lock: a running pass may itself be waiting for
        that lock, and join() while holding it would deadlock.
        """
        key = (camera_id or "").strip().lower()
        with self._state_lock:
            for bucket in (self._frame_counter, self._last_detections, self._last_detections_at):
                bucket.pop(key, None)
                if camera_id != key:
                    bucket.pop(camera_id, None)
            views = [v for k, v in list(self._live_views.items()) if k in (key, camera_id)]
            for v in views:
                self._live_views.pop(v._camera_id, None)
        for v in views:
            v.stop()

    def stop_all(self) -> None:
        """Stop every live detection worker (application shutdown).

        Without this a worker thread outlives the app and can be mid-inference
        during interpreter teardown, which shows up as the classic
        "terminate called without an active exception" on exit.
        """
        for camera_id in list(self._live_views):
            self.forget(camera_id)
        with self._state_lock:
            self._frame_counter.clear()
            self._last_detections.clear()
            self._last_detections_at.clear()


# Global singleton — the model is loaded once per backend process.
vehicle_detection_service = VehicleDetectionService()
