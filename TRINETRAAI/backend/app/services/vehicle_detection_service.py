"""
Real-time multi-vehicle detection for the annotated CCTV MJPEG view.

The old live-view implementation cached a set of YOLO boxes between inference
runs.  That made moving vehicles appear to stop and caused boxes to flicker or
duplicate when traffic was dense.  This service keeps the trained YOLO detector
but adds a per-view, PTS-driven ByteTrack-style association layer:

* COCO road-vehicle classes only (car, motorcycle, bus, truck and optional
  bicycle), so people and roadside objects are never drawn as vehicles.
* model NMS plus a conservative cross-pass duplicate guard, including optional
  overlapping tiles for distant high-resolution traffic.
* high-confidence detections start tracks immediately; lower-confidence
  candidates can only become visible after multi-frame confirmation and can
  rescue an existing track during an occlusion.
* every delivered frame advances the tracker.  If inference is deliberately
  throttled, boxes are predicted from measured video PTS rather than frozen.
* state is isolated per MJPEG viewing session and released when that stream
  closes, so one camera/viewer cannot corrupt another viewer's track IDs.

Ultralytics and torch stay lazy imports.  A missing model never interrupts a
camera feed: the response continues without overlays and logs only a safe,
non-secret diagnostic.
"""
from __future__ import annotations

import math
import os
import threading
from collections import OrderedDict
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from ..core.config import settings
from ..core.logging_config import logger

# COCO vehicle labels supported by the stock YOLO11 model.  "motorcycle" is
# the motorised bike class; bicycle is enabled separately because it is useful
# for mixed road scenes but can be turned off for motor-traffic-only cameras.
VEHICLE_CLASS_IDS: Dict[int, str] = {
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}
MOTOR_VEHICLE_CLASS_IDS: Tuple[int, ...] = (2, 3, 5, 7)
GREEN = (0, 255, 0)  # BGR — preserves the existing overlay colour.

# A stream PTS reset / multi-second gap denotes a new temporal scene.  Keeping
# identities through it produces ghost boxes, so state is reset instead.
_PTS_ROLLBACK_MS = 500.0
_PTS_GAP_MS = 5000.0
_EPS = 1e-6


@dataclass
class VehicleDetection:
    """A vehicle box in source-frame pixel coordinates."""

    x1: int
    y1: int
    x2: int
    y2: int
    class_name: str
    confidence: float
    class_id: int = -1
    track_id: Optional[int] = None
    predicted: bool = False

    @property
    def bbox(self) -> np.ndarray:
        return np.asarray((self.x1, self.y1, self.x2, self.y2), dtype=np.float32)

    @property
    def xyxy(self) -> Tuple[int, int, int, int]:
        return self.x1, self.y1, self.x2, self.y2


def _bbox_iou(a: Sequence[float], b: Sequence[float]) -> float:
    """Intersection-over-union for two xyxy boxes."""
    ax1, ay1, ax2, ay2 = (float(v) for v in a)
    bx1, by1, bx2, by2 = (float(v) for v in b)
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > _EPS else 0.0


def _intersection_over_smaller(a: Sequence[float], b: Sequence[float]) -> float:
    """Useful for suppressing a tile-edge fragment inside a full-frame box."""
    ax1, ay1, ax2, ay2 = (float(v) for v in a)
    bx1, by1, bx2, by2 = (float(v) for v in b)
    inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    smaller = min(area_a, area_b)
    return inter / smaller if smaller > _EPS else 0.0


def _clip_box(box: Sequence[float], frame_shape: Tuple[int, int]) -> Optional[np.ndarray]:
    """Clip a box to a frame and reject degenerate coordinates."""
    h, w = frame_shape
    if h <= 1 or w <= 1 or len(box) != 4:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in box)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
        return None
    x1, x2 = sorted((max(0.0, min(x1, w - 1.0)), max(0.0, min(x2, w - 1.0))))
    y1, y2 = sorted((max(0.0, min(y1, h - 1.0)), max(0.0, min(y2, h - 1.0))))
    if x2 - x1 < 1.0 or y2 - y1 < 1.0:
        return None
    return np.asarray((x1, y1, x2, y2), dtype=np.float32)


def _center_distance_ratio(a: Sequence[float], b: Sequence[float]) -> float:
    """Distance between box centres normalized by the larger box diagonal."""
    ax1, ay1, ax2, ay2 = (float(v) for v in a)
    bx1, by1, bx2, by2 = (float(v) for v in b)
    acx, acy = (ax1 + ax2) / 2.0, (ay1 + ay2) / 2.0
    bcx, bcy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0
    distance = math.hypot(acx - bcx, acy - bcy)
    diagonal_a = math.hypot(max(ax2 - ax1, 1.0), max(ay2 - ay1, 1.0))
    diagonal_b = math.hypot(max(bx2 - bx1, 1.0), max(by2 - by1, 1.0))
    return distance / max(diagonal_a, diagonal_b, 16.0)


def _as_numpy(value) -> np.ndarray:
    """Convert torch/cupy-like Ultralytics outputs without importing torch."""
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)


@dataclass
class _TrackedVehicle:
    track_id: int
    bbox: np.ndarray
    last_observed_bbox: np.ndarray
    velocity: np.ndarray
    class_scores: Dict[str, float]
    confidence: float
    first_pts_ms: float
    last_pts_ms: float
    last_detection_pts_ms: float
    required_hits: int
    hits: int = 1
    age_frames: int = 1
    time_since_detection_ms: float = 0.0

    @property
    def class_name(self) -> str:
        return max(self.class_scores, key=self.class_scores.get) if self.class_scores else "vehicle"

    @property
    def confirmed(self) -> bool:
        return self.hits >= self.required_hits


class _VehicleTracker:
    """Small PTS-driven, ByteTrack-style tracker for one MJPEG viewing session."""

    def __init__(
        self,
        *,
        high_confidence: float,
        max_age_sec: float,
        min_hits: int,
        low_confirm_hits: int,
        iou_threshold: float,
        max_center_distance: float,
    ) -> None:
        self.high_confidence = max(0.0, min(float(high_confidence), 1.0))
        self.max_age_ms = max(0.1, float(max_age_sec)) * 1000.0
        self.min_hits = max(1, int(min_hits))
        self.low_confirm_hits = max(2, int(low_confirm_hits))
        self.iou_threshold = max(0.0, min(float(iou_threshold), 1.0))
        self.max_center_distance = max(0.1, float(max_center_distance))
        self._tracks: List[_TrackedVehicle] = []
        self._next_id = 1
        self._last_pts_ms: Optional[float] = None

    def reset(self) -> None:
        self._tracks.clear()
        self._last_pts_ms = None

    @property
    def active_count(self) -> int:
        return len(self._tracks)

    def _elapsed_ms(self, pts_ms: float) -> float:
        if self._last_pts_ms is None:
            return 0.0
        return max(0.0, min(float(pts_ms) - self._last_pts_ms, _PTS_GAP_MS))

    def _advance(self, elapsed_ms: float, frame_shape: Tuple[int, int]) -> None:
        dt = elapsed_ms / 1000.0
        for track in self._tracks:
            if dt > 0.0:
                predicted = _clip_box(track.bbox + track.velocity * dt, frame_shape)
                if predicted is not None:
                    track.bbox = predicted
            track.time_since_detection_ms += elapsed_ms
            track.age_frames += 1

    def _association_score(self, track: _TrackedVehicle, detection: VehicleDetection) -> Optional[float]:
        det_box = detection.bbox
        overlap = _bbox_iou(track.bbox, det_box)
        containment = _intersection_over_smaller(track.bbox, det_box)
        center_ratio = _center_distance_ratio(track.bbox, det_box)

        # Preserve class stability but tolerate a momentary COCO class change
        # when the same physical box strongly overlaps (e.g. bus/truck angle).
        class_mismatch = detection.class_name != track.class_name
        if class_mismatch and overlap < 0.68 and containment < 0.88:
            return None

        # IoU does the primary work. Centre-distance gating keeps a partially
        # hidden or fast vehicle alive when its visible box changes shape.
        if overlap < self.iou_threshold and center_ratio > self.max_center_distance:
            return None
        if overlap <= 0.0 and center_ratio > min(self.max_center_distance, 0.80):
            return None

        centre_score = max(0.0, 1.0 - center_ratio / self.max_center_distance)
        score = overlap + 0.18 * centre_score + 0.06 * containment
        if class_mismatch:
            score -= 0.08
        return score

    def _associate(
        self,
        detections: Sequence[VehicleDetection],
        detection_indexes: Iterable[int],
        available_tracks: Iterable[int],
    ) -> List[Tuple[int, int]]:
        candidates: List[Tuple[float, int, int]] = []
        for det_index in detection_indexes:
            detection = detections[det_index]
            for track_index in available_tracks:
                score = self._association_score(self._tracks[track_index], detection)
                if score is not None:
                    candidates.append((score, det_index, track_index))
        candidates.sort(key=lambda item: item[0], reverse=True)

        used_detections = set()
        used_tracks = set()
        matches: List[Tuple[int, int]] = []
        for _, det_index, track_index in candidates:
            if det_index in used_detections or track_index in used_tracks:
                continue
            used_detections.add(det_index)
            used_tracks.add(track_index)
            matches.append((det_index, track_index))
        return matches

    def _update_track(
        self,
        track: _TrackedVehicle,
        detection: VehicleDetection,
        pts_ms: float,
        frame_shape: Tuple[int, int],
    ) -> None:
        observed = _clip_box(detection.bbox, frame_shape)
        if observed is None:
            return
        observed_elapsed_ms = max(0.0, pts_ms - track.last_detection_pts_ms)
        if observed_elapsed_ms > 1.0:
            observed_velocity = (observed - track.last_observed_bbox) / (observed_elapsed_ms / 1000.0)
            # A modest EMA absorbs detector jitter without making the overlay
            # lag visibly behind moving vehicles.
            track.velocity = 0.62 * track.velocity + 0.38 * observed_velocity

        # Blend the model measurement with its PTS prediction for stable boxes.
        track.bbox = 0.22 * track.bbox + 0.78 * observed
        clipped = _clip_box(track.bbox, frame_shape)
        track.bbox = clipped if clipped is not None else observed
        track.last_observed_bbox = observed
        track.last_detection_pts_ms = pts_ms
        track.last_pts_ms = pts_ms
        track.time_since_detection_ms = 0.0
        track.hits += 1
        track.confidence = min(1.0, 0.58 * track.confidence + 0.42 * float(detection.confidence))
        for name in list(track.class_scores):
            track.class_scores[name] *= 0.94
        track.class_scores[detection.class_name] = track.class_scores.get(detection.class_name, 0.0) + float(
            detection.confidence
        )

    def _new_track(
        self,
        detection: VehicleDetection,
        pts_ms: float,
        frame_shape: Tuple[int, int],
        required_hits: int,
    ) -> None:
        bbox = _clip_box(detection.bbox, frame_shape)
        if bbox is None:
            return
        self._tracks.append(
            _TrackedVehicle(
                track_id=self._next_id,
                bbox=bbox,
                last_observed_bbox=bbox.copy(),
                velocity=np.zeros(4, dtype=np.float32),
                class_scores={detection.class_name: float(detection.confidence)},
                confidence=float(detection.confidence),
                first_pts_ms=pts_ms,
                last_pts_ms=pts_ms,
                last_detection_pts_ms=pts_ms,
                required_hits=required_hits,
            )
        )
        self._next_id += 1

    def update(
        self,
        detections: Sequence[VehicleDetection],
        pts_ms: float,
        frame_shape: Tuple[int, int],
    ) -> List[VehicleDetection]:
        """Advance every frame and return one stable box for each visible track."""
        elapsed_ms = self._elapsed_ms(pts_ms)
        self._advance(elapsed_ms, frame_shape)
        cleaned = list(detections)

        high_indexes = [i for i, det in enumerate(cleaned) if det.confidence >= self.high_confidence]
        low_indexes = [i for i, det in enumerate(cleaned) if det.confidence < self.high_confidence]

        # ByteTrack's first association pass uses confident detections.  The
        # second pass lets weaker detections maintain an existing identity
        # without letting every weak one become a visible false positive.
        high_matches = self._associate(cleaned, high_indexes, range(len(self._tracks)))
        used_detections = {det_index for det_index, _ in high_matches}
        used_tracks = {track_index for _, track_index in high_matches}
        for det_index, track_index in high_matches:
            self._update_track(self._tracks[track_index], cleaned[det_index], pts_ms, frame_shape)

        remaining_tracks = [i for i in range(len(self._tracks)) if i not in used_tracks]
        low_matches = self._associate(cleaned, low_indexes, remaining_tracks)
        for det_index, track_index in low_matches:
            used_detections.add(det_index)
            used_tracks.add(track_index)
            self._update_track(self._tracks[track_index], cleaned[det_index], pts_ms, frame_shape)

        # Birth tracks after association.  A strong new object is visible
        # immediately; a low-confidence distant object needs repeat evidence.
        for det_index, detection in enumerate(cleaned):
            if det_index in used_detections:
                continue
            required_hits = self.min_hits if detection.confidence >= self.high_confidence else self.low_confirm_hits
            self._new_track(detection, pts_ms, frame_shape, required_hits)

        # Tentative low-confidence tracks disappear sooner, while confirmed
        # tracks survive a short detector miss/partial occlusion.
        kept: List[_TrackedVehicle] = []
        for track in self._tracks:
            lifetime = self.max_age_ms if track.confirmed else min(self.max_age_ms, 650.0)
            if track.time_since_detection_ms <= lifetime:
                kept.append(track)
        self._tracks = kept
        self._last_pts_ms = pts_ms

        visible: List[VehicleDetection] = []
        for track in self._tracks:
            if not track.confirmed:
                continue
            box = _clip_box(track.bbox, frame_shape)
            if box is None:
                continue
            x1, y1, x2, y2 = (int(round(v)) for v in box)
            visible.append(
                VehicleDetection(
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    class_name=track.class_name,
                    confidence=float(track.confidence),
                    track_id=track.track_id,
                    predicted=track.time_since_detection_ms > 0.0,
                )
            )
        return visible


@dataclass
class _CameraDetectionState:
    tracker: _VehicleTracker
    lock: threading.RLock = field(default_factory=threading.RLock)
    frame_counter: int = 0
    inference_counter: int = 0
    last_pts_ms: Optional[float] = None
    last_frame_key: Optional[object] = None
    frame_shape: Optional[Tuple[int, int]] = None
    tracks: List[VehicleDetection] = field(default_factory=list)


class VehicleDetectionService:
    """Shared lazy YOLO model plus isolated per-live-view tracking state."""

    def __init__(self) -> None:
        self._model = None
        self._model_lock = threading.Lock()
        # Ultralytics models are not safe to infer concurrently from arbitrary
        # request threads.  Serialize only inference, never capture/UI work.
        self._infer_lock = threading.Lock()
        self._disabled_reason: Optional[str] = None
        self._states: Dict[str, _CameraDetectionState] = {}
        self._states_lock = threading.RLock()
        # Resident capture packets are shared by all MJPEG viewers of a camera.
        # Cache their immutable raw YOLO results briefly so opening a second
        # dashboard tile does not queue a duplicate model invocation. Trackers
        # remain session-isolated below.
        self._shared_frame_results: OrderedDict[Tuple[object, bool], List[VehicleDetection]] = OrderedDict()
        self._shared_frame_results_lock = threading.RLock()
        self._shared_frame_result_limit = 128
        self.last_inference_ms: Optional[float] = None
        self.frames_inferred = 0

    # ------------------------------------------------------------------ model
    @property
    def enabled(self) -> bool:
        return bool(getattr(settings, "VEHICLE_DETECTION_ENABLED", True)) and self._disabled_reason is None

    @property
    def disabled_reason(self) -> Optional[str]:
        """Safe availability diagnostic; never contains a camera source URL."""
        return self._disabled_reason

    @staticmethod
    def _vehicle_class_ids() -> List[int]:
        if bool(getattr(settings, "DETECTION_INCLUDE_BICYCLES", True)):
            return sorted(VEHICLE_CLASS_IDS)
        return list(MOTOR_VEHICLE_CLASS_IDS)

    def _resolve_model_path(self) -> str:
        """Find configured weights or let Ultralytics obtain its official asset."""
        configured = (getattr(settings, "YOLO_MODEL_PATH", "") or "yolo11n.pt").strip()
        candidates = [configured]
        backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        candidates.append(os.path.join(backend_root, configured))
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
        return os.path.basename(configured) or "yolo11n.pt"

    def _model_kwargs(self) -> dict:
        return {
            "verbose": False,
            "conf": max(0.01, min(float(getattr(settings, "DETECTION_LOW_CONFIDENCE", 0.20)), 0.99)),
            "iou": max(0.05, min(float(getattr(settings, "DETECTION_NMS_IOU_THRESHOLD", 0.70)), 0.99)),
            "imgsz": max(32, int(getattr(settings, "DETECTION_IMGSZ", 960))),
            "device": getattr(settings, "DETECTION_DEVICE", "cpu") or "cpu",
            "classes": self._vehicle_class_ids(),
            "max_det": max(1, int(getattr(settings, "DETECTION_MAX_DETECTIONS", 300))),
            "agnostic_nms": False,
        }

    def _ensure_model(self):
        if self._model is not None or self._disabled_reason is not None:
            return self._model
        with self._model_lock:
            if self._model is not None or self._disabled_reason is not None:
                return self._model
            try:
                from ultralytics import YOLO  # lazy: heavy optional dependency

                path = self._resolve_model_path()
                logger.info("[DETECTION] Loading shared YOLO vehicle model: %s", path)
                started = time.perf_counter()
                model = YOLO(path)
                # Warm up once so opening a live camera does not pay compilation
                # latency on its first visible frame.
                size = max(32, int(getattr(settings, "DETECTION_IMGSZ", 960)))
                model.predict(np.zeros((size, size, 3), dtype=np.uint8), **self._model_kwargs())
                self._model = model
                logger.info("[DETECTION] YOLO model ready in %.1fs", time.perf_counter() - started)
            except Exception as exc:  # package/weights/device unavailable
                self._disabled_reason = f"model unavailable: {type(exc).__name__}"
                logger.warning("[DETECTION] Vehicle overlays unavailable (%s); video remains live.", self._disabled_reason)
        return self._model

    # -------------------------------------------------------------- inference
    @staticmethod
    def _tile_regions(frame: np.ndarray) -> List[Tuple[int, int, np.ndarray]]:
        """Build an optional overlapping grid while retaining the full frame."""
        grid = max(1, int(getattr(settings, "DETECTION_TILE_GRID", 1)))
        min_edge = max(1, int(getattr(settings, "DETECTION_TILE_MIN_FRAME_EDGE", 1400)))
        h, w = frame.shape[:2]
        if grid <= 1 or max(h, w) < min_edge:
            return [(0, 0, frame)]

        overlap = max(0.0, min(float(getattr(settings, "DETECTION_TILE_OVERLAP", 0.20)), 0.45))
        # Two 60%-wide tiles overlap by 20%; this avoids losing a small vehicle
        # precisely on a tile edge.  The full frame preserves very large buses.
        divisor = grid - (grid - 1) * overlap
        tile_w = min(w, max(1, int(math.ceil(w / divisor))))
        tile_h = min(h, max(1, int(math.ceil(h / divisor))))
        xs = [0] if grid == 1 else [int(round(i * (w - tile_w) / (grid - 1))) for i in range(grid)]
        ys = [0] if grid == 1 else [int(round(i * (h - tile_h) / (grid - 1))) for i in range(grid)]

        regions: List[Tuple[int, int, np.ndarray]] = [(0, 0, frame)]
        for y in ys:
            for x in xs:
                regions.append((x, y, frame[y : y + tile_h, x : x + tile_w]))
        return regions

    @staticmethod
    def _deduplicate(detections: Sequence[VehicleDetection]) -> List[VehicleDetection]:
        """Remove only near-identical model/tile boxes, not nearby vehicles."""
        threshold = max(0.50, min(float(getattr(settings, "DETECTION_DUPLICATE_IOU_THRESHOLD", 0.82)), 0.99))
        kept: List[VehicleDetection] = []
        for candidate in sorted(detections, key=lambda item: item.confidence, reverse=True):
            duplicate = False
            for existing in kept:
                overlap = _bbox_iou(candidate.bbox, existing.bbox)
                containment = _intersection_over_smaller(candidate.bbox, existing.bbox)
                same_class = candidate.class_name == existing.class_name
                # Cross-class suppression is stricter so a motorcycle in front
                # of a bus/car remains a separate vehicle.
                needed = threshold if same_class else max(0.92, threshold)
                if overlap >= needed or (same_class and containment >= max(0.92, threshold + 0.08)):
                    duplicate = True
                    break
            if not duplicate:
                kept.append(candidate)
        return kept

    def detect(self, frame: np.ndarray, *, use_tiling: bool = False) -> List[VehicleDetection]:
        """Run trained YOLO on one BGR frame and return de-duplicated vehicles."""
        model = self._ensure_model()
        if model is None or frame is None or frame.size == 0:
            return []

        frame_shape = frame.shape[:2]
        min_area = max(1.0, float(getattr(settings, "DETECTION_MIN_BOX_AREA", 9.0)))
        low_confidence = max(0.01, min(float(getattr(settings, "DETECTION_LOW_CONFIDENCE", 0.20)), 0.99))
        accepted_classes = set(self._vehicle_class_ids())
        started = time.perf_counter()
        detections: List[VehicleDetection] = []
        regions = self._tile_regions(frame) if use_tiling else [(0, 0, frame)]

        try:
            with self._infer_lock:
                for offset_x, offset_y, image in regions:
                    results = model.predict(image, **self._model_kwargs())
                    if not results:
                        continue
                    result = results[0]
                    boxes = getattr(result, "boxes", None)
                    if boxes is None:
                        continue
                    xyxy = _as_numpy(boxes.xyxy)
                    confidences = _as_numpy(boxes.conf).reshape(-1)
                    classes = _as_numpy(boxes.cls).reshape(-1)
                    for box, confidence, class_id_raw in zip(xyxy, confidences, classes):
                        try:
                            class_id = int(class_id_raw)
                            confidence_value = float(confidence)
                        except (TypeError, ValueError):
                            continue
                        class_name = VEHICLE_CLASS_IDS.get(class_id)
                        if (
                            confidence_value < low_confidence
                            or class_id not in accepted_classes
                            or class_name is None
                        ):
                            continue
                        clipped = _clip_box(
                            (
                                float(box[0]) + offset_x,
                                float(box[1]) + offset_y,
                                float(box[2]) + offset_x,
                                float(box[3]) + offset_y,
                            ),
                            frame_shape,
                        )
                        if clipped is None:
                            continue
                        if (clipped[2] - clipped[0]) * (clipped[3] - clipped[1]) < min_area:
                            continue
                        detections.append(
                            VehicleDetection(
                                x1=int(round(clipped[0])),
                                y1=int(round(clipped[1])),
                                x2=int(round(clipped[2])),
                                y2=int(round(clipped[3])),
                                class_name=class_name,
                                confidence=confidence_value,
                                class_id=class_id,
                            )
                        )
        except Exception as exc:
            logger.error("[DETECTION] Inference failed (%s); retaining live video.", type(exc).__name__)
            return []

        self.last_inference_ms = (time.perf_counter() - started) * 1000.0
        self.frames_inferred += 1
        return self._deduplicate(detections)

    def _detections_for_packet(
        self,
        frame: np.ndarray,
        *,
        use_tiling: bool,
        shared_frame_key: Optional[object],
    ) -> List[VehicleDetection]:
        """Infer once per resident packet while keeping each viewer's tracks private."""
        if shared_frame_key is None:
            return self.detect(frame, use_tiling=use_tiling)
        cache_key = (shared_frame_key, bool(use_tiling))
        # Keep the small cache lock through inference. That is intentional: a
        # simultaneous viewer waits for the first result instead of submitting
        # a second identical YOLO job behind the model lock.
        with self._shared_frame_results_lock:
            cached = self._shared_frame_results.get(cache_key)
            if cached is not None:
                self._shared_frame_results.move_to_end(cache_key)
                return list(cached)
            detections = self.detect(frame, use_tiling=use_tiling)
            self._shared_frame_results[cache_key] = list(detections)
            while len(self._shared_frame_results) > self._shared_frame_result_limit:
                self._shared_frame_results.popitem(last=False)
            return detections

    # --------------------------------------------------------------- tracking
    @staticmethod
    def _make_tracker() -> _VehicleTracker:
        return _VehicleTracker(
            high_confidence=float(getattr(settings, "CONFIDENCE_THRESHOLD", 0.35)),
            max_age_sec=float(getattr(settings, "DETECTION_TRACK_MAX_AGE_SEC", 1.25)),
            min_hits=int(getattr(settings, "DETECTION_TRACK_MIN_HITS", 1)),
            low_confirm_hits=int(getattr(settings, "DETECTION_LOW_CONFIDENCE_CONFIRM_HITS", 2)),
            iou_threshold=float(getattr(settings, "DETECTION_TRACK_IOU_THRESHOLD", 0.18)),
            max_center_distance=float(getattr(settings, "DETECTION_TRACK_CENTER_DISTANCE", 1.35)),
        )

    def _state_for(self, session_key: str) -> _CameraDetectionState:
        with self._states_lock:
            state = self._states.get(session_key)
            if state is None:
                state = _CameraDetectionState(tracker=self._make_tracker())
                self._states[session_key] = state
            return state

    @staticmethod
    def _normalised_pts(state: _CameraDetectionState, pts_ms: Optional[float]) -> float:
        try:
            pts = float(pts_ms) if pts_ms is not None else float("nan")
        except (TypeError, ValueError):
            pts = float("nan")
        if math.isfinite(pts):
            return pts
        # Capture code supplies container PTS whenever it is available.  This
        # monotonic stream-clock fallback only handles opaque sources that do
        # not expose it; it never assumes a nominal FPS.
        return time.monotonic() * 1000.0

    @staticmethod
    def _needs_reset(state: _CameraDetectionState, pts_ms: float, frame_shape: Tuple[int, int]) -> bool:
        if state.frame_shape is not None and state.frame_shape != frame_shape:
            return True
        if state.last_pts_ms is None:
            return False
        return pts_ms < state.last_pts_ms - _PTS_ROLLBACK_MS or pts_ms - state.last_pts_ms > _PTS_GAP_MS

    # ---------------------------------------------------------------- drawing
    @staticmethod
    def draw(frame: np.ndarray, detections: Sequence[VehicleDetection]) -> np.ndarray:
        """Draw one green class/confidence box per stable vehicle track."""
        if frame is None or frame.size == 0:
            return frame
        h, w = frame.shape[:2]
        show_ids = bool(getattr(settings, "DETECTION_SHOW_TRACK_IDS", False))
        for detection in detections:
            x1 = max(0, min(int(detection.x1), w - 1))
            y1 = max(0, min(int(detection.y1), h - 1))
            x2 = max(x1 + 1, min(int(detection.x2), w - 1))
            y2 = max(y1 + 1, min(int(detection.y2), h - 1))
            cv2.rectangle(frame, (x1, y1), (x2, y2), GREEN, 2)
            label = f"{detection.class_name} {detection.confidence:.2f}"
            if show_ids and detection.track_id is not None:
                label = f"{label} #{detection.track_id}"
            (text_width, text_height), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            text_baseline = y1 - 6 if y1 - text_height - 8 > 0 else min(h - 3, y1 + text_height + 6)
            box_top = max(0, text_baseline - text_height - 4)
            box_right = min(w - 1, x1 + text_width + 6)
            cv2.rectangle(frame, (x1, box_top), (box_right, min(h - 1, text_baseline + 4)), GREEN, -1)
            cv2.putText(
                frame,
                label,
                (min(w - 2, x1 + 3), text_baseline),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 0),
                1,
                cv2.LINE_AA,
            )
        return frame

    # --------------------------------------------------------------- pipeline
    def annotate(
        self,
        session_key: str,
        frame: np.ndarray,
        *,
        pts_ms: Optional[float] = None,
        frame_key: Optional[object] = None,
        shared_frame_key: Optional[object] = None,
        is_discontinuity: bool = False,
    ) -> np.ndarray:
        """Advance the per-view detector/tracker and annotate one live frame.

        ``frame_key`` avoids running inference repeatedly when one MJPEG client
        asks faster than its resident capture worker produces frames. Optional
        ``shared_frame_key`` lets simultaneous viewers reuse one raw inference
        for the same resident packet; their tracker identities remain isolated.
        """
        if not self.enabled or frame is None or frame.size == 0:
            return frame

        state = self._state_for(session_key)
        frame_shape = frame.shape[:2]
        with state.lock:
            current_pts = self._normalised_pts(state, pts_ms)
            if is_discontinuity or self._needs_reset(state, current_pts, frame_shape):
                state.tracker.reset()
                state.tracks = []
                state.last_frame_key = None

            # A resident worker may expose the same packet more than once as
            # the browser consumes MJPEG. Draw its last tracks but do not age,
            # re-infer, or mutate identities for a duplicate packet.
            if frame_key is not None and frame_key == state.last_frame_key:
                return self.draw(frame, state.tracks)

            state.frame_counter += 1
            every_n = max(1, int(getattr(settings, "DETECTION_EVERY_N_FRAMES", 1)))
            should_infer = (state.frame_counter - 1) % every_n == 0
            raw_detections: List[VehicleDetection] = []
            if should_infer:
                state.inference_counter += 1
                tiled_every = max(1, int(getattr(settings, "DETECTION_TILE_EVERY_N_INFERENCES", 4)))
                wants_tiles = (
                    int(getattr(settings, "DETECTION_TILE_GRID", 1)) > 1
                    and (state.inference_counter - 1) % tiled_every == 0
                )
                raw_detections = self._detections_for_packet(
                    frame,
                    use_tiling=wants_tiles,
                    shared_frame_key=shared_frame_key,
                )

            state.tracks = state.tracker.update(raw_detections, current_pts, frame_shape)
            state.last_pts_ms = current_pts
            state.frame_shape = frame_shape
            state.last_frame_key = frame_key
            return self.draw(frame, state.tracks)

    def tracks_for(self, session_key: str) -> List[VehicleDetection]:
        """Return a copy of current stable tracks; useful for non-UI diagnostics/tests."""
        state = self._state_for(session_key)
        with state.lock:
            return list(state.tracks)

    def forget(self, session_key: str) -> None:
        """Release per-view tracker state when its MJPEG connection closes."""
        with self._states_lock:
            self._states.pop(session_key, None)


# Global singleton — model weights are loaded once per backend process.
vehicle_detection_service = VehicleDetectionService()
