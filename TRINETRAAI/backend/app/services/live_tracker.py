"""Live adapter for TRINETRA's own PTS-driven Kalman/two-stage-IoU tracker.

One instance per camera. No second YOLO call and no dependency on either of the
external reference repositories. Raw observations (not predictions) feed OCR,
photo evidence and counting. SimpleTracker remains an explicit rollback option.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

from ..core.config import settings
from .simple_tracker import SimpleTracker, TrackedBox


class LiveTracker:
    def __init__(self):
        self.name = settings.LIVE_ANPR_TRACKER
        self._tracks: dict[int, TrackedBox] = {}
        if self.name == "iou":
            self._tracker = SimpleTracker(max_misses=3)
        else:
            # Lazy numpy import: the API can still boot without vision extras.
            from .motion_tracker_core import VehicleTracker
            self._tracker = VehicleTracker(
                min_hits=1,  # photo preview is immediate; counts/OCR confirm separately
                max_age_sec=max(5.0, 3 * settings.LIVE_ANPR_SAMPLE_SECONDS),
                max_tracks=max(32, settings.LIVE_ANPR_MAX_TRACKED_VEHICLES * 4),
            )

    def update(self, boxes, time_s):
        if self.name == "iou":
            return self._tracker.update(boxes)
        detections = [SimpleNamespace(bbox=list(b[:4]), class_name=b[4], confidence=b[5], camera_id=None)
                      for b in boxes if all(math.isfinite(float(v)) for v in (*b[:4], b[5]))]
        tracks = self._tracker.update(detections, pts_ms=time_s * 1000)
        current = {}
        for track in tracks:
            previous = self._tracks.get(track.track_id)
            observed = track.time_since_update_ms == 0
            box = track.observed_bbox or track.bbox
            current[track.track_id] = TrackedBox(
                track.track_id, *[int(v) for v in box], track.class_name, track.confidence,
                hits=track.hits, misses=0 if observed else (previous.misses + 1 if previous else 1),
            )
        retired = [track for key, track in self._tracks.items() if key not in current]
        self._tracks = current
        return list(current.values()), retired
