"""Vehicle tracking with ByteTrack (via ultralytics).

One inference per frame feeds *both* detection and tracking: ``model.track()``
runs the detector and hands the boxes to ByteTrack in the same call, so the
pipeline never pays for two forward passes.

Timing contract: every track carries the frame's PTS. Track age is measured in
PTS seconds, never in frames, because Sentinel feeds drop frames and the
inter-frame gap is not constant.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from config.settings import Settings
from detection.classes import COCO_VEHICLE_CLASSES, VEHICLE_CLASS_IDS
from detection.vehicle_detector import resolve_device, resolve_model_path
from logging_setup import log_event

log = logging.getLogger("trinetra.track")


@dataclass
class TrackedVehicle:
    """One tracked vehicle in one frame."""

    track_id: int
    bbox: tuple[float, float, float, float]
    class_name: str
    confidence: float
    camera_id: str
    pts_ms: float
    continuous_ms: float = 0.0
    class_id: int | None = None
    #: PTS (ms) of the first frame in which this track was seen.
    first_seen_pts_ms: float = 0.0
    frames_seen: int = 1

    @property
    def dwell_s(self) -> float:
        """How long this vehicle has been in view, from PTS — not frame count."""
        return max(0.0, (self.continuous_ms - self.first_seen_pts_ms) / 1000.0)

    def crop(self, frame: np.ndarray) -> Optional[np.ndarray]:
        h, w = frame.shape[:2]
        x1 = int(max(0, min(self.bbox[0], w - 1)))
        y1 = int(max(0, min(self.bbox[1], h - 1)))
        x2 = int(max(x1 + 1, min(self.bbox[2], w)))
        y2 = int(max(y1 + 1, min(self.bbox[3], h)))
        crop = frame[y1:y2, x1:x2]
        return crop if crop.size else None

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "bbox": [round(v, 2) for v in self.bbox],
            "class": self.class_name,
            "confidence": round(self.confidence, 4),
            "camera_id": self.camera_id,
            "pts_ms": self.pts_ms,
            "dwell_s": round(self.dwell_s, 2),
        }


@dataclass
class _TrackMemory:
    first_seen_pts_ms: float
    continuous_ms: float
    frames_seen: int = 1
    class_votes: dict = field(default_factory=dict)


class VehicleTracker:
    """ByteTrack wrapper with PTS-based ageing and scene-cut recovery."""

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
        self._memory: dict[int, _TrackMemory] = {}
        self.track_ms_total = 0.0
        self.track_count = 0
        self.resets = 0
        self.max_track_id_seen = 0

    # -- model --------------------------------------------------------------
    @property
    def model(self):
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
                tracker=self.settings.tracker_config,
            )
        return self._model

    # -- tracking -----------------------------------------------------------
    def update(
        self,
        frame: np.ndarray,
        camera_id: str,
        pts_ms: float,
        continuous_ms: float = 0.0,
    ) -> list[TrackedVehicle]:
        """Track one frame. Returns the currently active tracked vehicles."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return []
        started = time.perf_counter()
        results = self.model.track(
            frame,
            persist=True,
            tracker=self.settings.tracker_config,
            conf=self.settings.conf_threshold,
            iou=self.settings.iou_threshold,
            imgsz=self.settings.imgsz,
            device=self.device,
            classes=list(self.class_ids),
            verbose=False,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.track_ms_total += elapsed_ms
        self.track_count += 1

        tracks = self._parse(
            results[0] if results else None, camera_id, pts_ms, continuous_ms
        )
        self.prune(continuous_ms)
        return tracks

    def _parse(self, result, camera_id: str, pts_ms: float, continuous_ms: float) -> list[TrackedVehicle]:
        if result is None or getattr(result, "boxes", None) is None:
            return []
        boxes = result.boxes
        ids = getattr(boxes, "id", None)
        if ids is None:
            # ByteTrack has not confirmed any track yet (first frames). The
            # detections are real, but we do not invent identities for them.
            return []
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        classes = boxes.cls.cpu().numpy().astype(int)
        track_ids = ids.cpu().numpy().astype(int)
        names = getattr(result, "names", COCO_VEHICLE_CLASSES) or {}

        tracks: list[TrackedVehicle] = []
        for box, conf, cls, tid in zip(xyxy, confs, classes, track_ids):
            if int(cls) not in COCO_VEHICLE_CLASSES:
                continue
            tid = int(tid)
            memory = self._memory.get(tid)
            if memory is None:
                memory = _TrackMemory(
                    first_seen_pts_ms=continuous_ms or pts_ms,
                    continuous_ms=continuous_ms or pts_ms,
                )
                self._memory[tid] = memory
                log_event(
                    log,
                    "track_started",
                    level=logging.DEBUG,
                    camera=camera_id,
                    track_id=tid,
                    cls=names.get(int(cls), "?"),
                    pts_ms=pts_ms,
                )
            else:
                memory.frames_seen += 1
                memory.continuous_ms = continuous_ms or pts_ms
            memory.class_votes[str(names.get(int(cls), COCO_VEHICLE_CLASSES[int(cls)]))] = (
                memory.class_votes.get(str(names.get(int(cls))), 0) + 1
            )
            self.max_track_id_seen = max(self.max_track_id_seen, tid)
            tracks.append(
                TrackedVehicle(
                    track_id=tid,
                    bbox=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                    class_name=str(names.get(int(cls), COCO_VEHICLE_CLASSES[int(cls)])),
                    confidence=float(conf),
                    camera_id=camera_id,
                    pts_ms=float(pts_ms),
                    continuous_ms=float(continuous_ms or pts_ms),
                    class_id=int(cls),
                    first_seen_pts_ms=memory.first_seen_pts_ms,
                    frames_seen=memory.frames_seen,
                )
            )
        tracks.sort(key=lambda t: t.track_id)
        return tracks

    # -- lifecycle ----------------------------------------------------------
    def prune(self, continuous_ms: float) -> list[int]:
        """Drop tracks not updated within ``track_max_age_s`` (PTS seconds)."""
        if not continuous_ms:
            return []
        max_age_ms = self.settings.track_max_age_s * 1000.0
        stale = [
            tid
            for tid, mem in self._memory.items()
            if (continuous_ms - mem.continuous_ms) > max_age_ms
        ]
        for tid in stale:
            del self._memory[tid]
        return stale

    def reset(self, reason: str = "scene_cut") -> None:
        """Forget every track. Called on a hard scene cut / stream restart."""
        self.resets += 1
        dropped = len(self._memory)
        self._memory.clear()
        tracker = self._underlying_tracker()
        if tracker is not None and hasattr(tracker, "reset"):
            try:
                tracker.reset()
            except Exception as exc:  # noqa: BLE001 - tracker internals vary by version
                log_event(
                    log,
                    "tracker_reset_failed",
                    level=logging.WARNING,
                    error=f"{type(exc).__name__}: {exc}",
                )
        log_event(
            log,
            "tracking_state_reset",
            level=logging.WARNING,
            reason=reason,
            tracks_dropped=dropped,
        )

    def _underlying_tracker(self):
        predictor = getattr(self._model, "predictor", None)
        trackers = getattr(predictor, "trackers", None) if predictor else None
        if trackers:
            return trackers[0]
        return None

    # -- metrics ------------------------------------------------------------
    @property
    def avg_track_ms(self) -> float:
        return self.track_ms_total / self.track_count if self.track_count else 0.0

    @property
    def active_tracks(self) -> int:
        return len(self._memory)

    def dominant_class(self, track_id: int) -> str | None:
        """Most-voted class for a track — absorbs single-frame class flicker."""
        memory = self._memory.get(track_id)
        if not memory or not memory.class_votes:
            return None
        return max(memory.class_votes.items(), key=lambda kv: kv[1])[0]
