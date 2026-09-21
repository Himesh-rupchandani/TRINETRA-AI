"""
Multi-object vehicle tracking (spec §13, §14).

ByteTrack-style association (two-stage IoU matching: confident detections
first, weaker detections rescue unmatched tracks) over a constant-velocity
Kalman motion model.

Timing contract (spec §10): the tracker is driven by PTS deltas computed from
the frames it receives — never by wall-clock arrival time and never by an
assumed constant frame interval. dt is passed explicitly into the motion
model; track lifetimes (age, time_since_update) are measured in PTS-ms.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

logger = logging.getLogger("cv_engine.tracking")

DEFAULT_DT_SEC = 0.04      # motion-model step when PTS delta unavailable
MAX_DT_SEC = 2.0           # clamp huge PTS gaps (decode stalls)
COUNT = 0


def iou_matrix(boxes_a: np.ndarray, boxes_b: np.ndarray) -> np.ndarray:
    """IoU between two [N,4] / [M,4] xyxy arrays -> [N,M]."""
    if len(boxes_a) == 0 or len(boxes_b) == 0:
        return np.zeros((len(boxes_a), len(boxes_b)), dtype=np.float32)
    ax1, ay1, ax2, ay2 = boxes_a[:, 0], boxes_a[:, 1], boxes_a[:, 2], boxes_a[:, 3]
    bx1, by1, bx2, by2 = boxes_b[:, 0], boxes_b[:, 1], boxes_b[:, 2], boxes_b[:, 3]

    xx1 = np.maximum(ax1[:, None], bx1[None, :])
    yy1 = np.maximum(ay1[:, None], by1[None, :])
    xx2 = np.minimum(ax2[:, None], bx2[None, :])
    yy2 = np.minimum(ay2[:, None], by2[None, :])

    inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
    area_a = np.clip(ax2 - ax1, 0, None) * np.clip(ay2 - ay1, 0, None)
    area_b = np.clip(bx2 - bx1, 0, None) * np.clip(by2 - by1, 0, None)
    union = area_a[:, None] + area_b[None, :] - inter
    return np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0).astype(np.float32)


class _KalmanBox:
    """
    Constant-velocity Kalman filter (SORT-style) over
    state = [cx, cy, area, aspect, vx, vy, v_area, v_aspect].
    dt scales the state transition, so PTS gaps drive the motion model.
    """

    def __init__(self, bbox_xyxy: Sequence[float]):
        z = self._z(bbox_xyxy)
        self.x = np.concatenate([z, np.zeros(4)], dtype=np.float64)
        self.P = np.eye(8, dtype=np.float64)
        self.P[4:, 4:] *= 1000.0  # high uncertainty on velocities
        self.P *= 10.0
        self.H = np.zeros((4, 8), dtype=np.float64)
        self.H[:, :4] = np.eye(4)
        self.R = np.eye(4, dtype=np.float64)

    @staticmethod
    def _z(bbox_xyxy: Sequence[float]) -> np.ndarray:
        x1, y1, x2, y2 = bbox_xyxy
        w = max(float(x2) - float(x1), 1e-3)
        h = max(float(y2) - float(y1), 1e-3)
        return np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0, w * h, w / h], dtype=np.float64)

    def predict(self, dt: float) -> np.ndarray:
        dt = float(np.clip(dt, 0.0, MAX_DT_SEC))
        F = np.eye(8, dtype=np.float64)
        for i in range(4):
            F[i, 4 + i] = dt  # position/shape integrates its velocity * dt
        Q = np.eye(8, dtype=np.float64) * max(dt, 1e-3)
        Q[4:, 4:] *= 0.01
        self.x = F @ self.x
        self.x[2] = max(self.x[2], 1e-3)  # area stays positive
        self.P = F @ self.P @ F.T + Q
        return self.bbox()

    def update(self, bbox_xyxy: Sequence[float]) -> None:
        z = self._z(bbox_xyxy)
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ (z - self.H @ self.x)
        self.P = (np.eye(8) - K @ self.H) @ self.P

    def bbox(self) -> List[float]:
        cx, cy, area, aspect = self.x[:4]
        area = max(float(area), 1e-3)
        aspect = max(float(aspect), 1e-3)
        w = float(np.sqrt(area * aspect))
        h = float(area / max(w, 1e-3))
        return [cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0]


@dataclass
class Track:
    track_id: int
    bbox: List[float]
    class_name: str
    confidence: float
    camera_id: Optional[str] = None
    first_pts_ms: Optional[float] = None
    last_pts_ms: Optional[float] = None
    hits: int = 1
    frames: int = 1
    time_since_update_ms: float = 0.0  # PTS-based, not arrival-time based
    # Raw measurement, never a Kalman prediction. Only current observations
    # may be cropped, OCR'd or used to generate a crossing.
    observed_bbox: Optional[List[float]] = None

    @property
    def confirmed_age_ms(self) -> Optional[float]:
        if self.first_pts_ms is None or self.last_pts_ms is None:
            return None
        return self.last_pts_ms - self.first_pts_ms

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "bbox": self.bbox,
            "class": self.class_name,
            "confidence": self.confidence,
            "camera_id": self.camera_id,
            "pts_ms": self.last_pts_ms,
        }


class _TrackState:
    __slots__ = (
        "track_id", "kf", "cls", "conf", "hits", "frames",
        "first_pts", "last_pts", "since_update_ms", "camera_id", "observed_bbox",
    )

    def __init__(self, track_id, bbox, cls, conf, pts_ms, camera_id):
        self.track_id = track_id
        self.kf = _KalmanBox(bbox)
        self.cls = cls
        self.conf = conf
        self.hits = 1
        self.frames = 1
        self.first_pts = pts_ms
        self.last_pts = pts_ms
        self.since_update_ms = 0.0
        self.camera_id = camera_id
        self.observed_bbox = list(bbox)


class VehicleTracker:
    """
    PTS-driven ByteTrack-style tracker.

    update(detections, pts_ms) returns the list of currently confirmed tracks.
    Call reset() on scene discontinuity (feed loop / hard cut).
    """

    def __init__(
        self,
        max_age_sec: float = 1.5,
        min_hits: int = 2,
        iou_threshold: float = 0.25,
        high_conf: float = 0.5,
        low_conf: float = 0.1,
        max_tracks: int = 128,
    ):
        self.max_age_ms = max_age_sec * 1000.0
        self.min_hits = max(1, min_hits)
        self.iou_threshold = iou_threshold
        self.high_conf = high_conf
        self.low_conf = low_conf
        self.max_tracks = max(1, int(max_tracks))
        self._tracks: List[_TrackState] = []
        self._next_id = 1
        self._last_pts: Optional[float] = None
        self.resets = 0

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Drop all tracks (scene discontinuity / reconnect). Spec §14."""
        if self._tracks:
            logger.info("[TRACKER] scene reset: dropping %d track(s)", len(self._tracks))
        self._tracks = []
        self._last_pts = None
        self.resets += 1

    def _new_id(self) -> int:
        tid = self._next_id
        self._next_id += 1
        return tid

    # ------------------------------------------------------------------
    def _compute_dt_sec(self, pts_ms: Optional[float]) -> float:
        """PTS-based elapsed time since last update (spec §10)."""
        if pts_ms is None or self._last_pts is None:
            return DEFAULT_DT_SEC
        dt_ms = pts_ms - self._last_pts
        if dt_ms <= 0:
            return DEFAULT_DT_SEC  # PTS rollback handled upstream as discontinuity
        return float(min(dt_ms / 1000.0, MAX_DT_SEC))

    def update(self, detections: Sequence, pts_ms: Optional[float] = None) -> List[Track]:
        """
        Consume one frame's detections (with PTS) and return confirmed tracks.
        `detections` items need .bbox, .class_name, .confidence, .camera_id.
        """
        dt = self._compute_dt_sec(pts_ms)

        # 1) Predict every existing track forward by the PTS delta.
        for tr in self._tracks:
            tr.kf.predict(dt)
            if self._last_pts is not None and pts_ms is not None and pts_ms > self._last_pts:
                tr.since_update_ms += pts_ms - self._last_pts
            elif pts_ms is None:
                tr.since_update_ms += dt * 1000.0
            tr.frames += 1

        # Expire BEFORE association: a late box must not resurrect an old ID.
        self._tracks = [t for t in self._tracks if t.since_update_ms <= self.max_age_ms]
        dets = list(detections)
        det_boxes = np.array([d.bbox for d in dets], dtype=np.float32) if dets else np.zeros((0, 4))

        matched_ids = set()
        matched_det_idx = set()

        def associate(det_indices: Sequence[int]) -> None:
            if not det_indices or not self._tracks:
                return
            track_boxes = np.array([t.kf.bbox() for t in self._tracks], dtype=np.float32)
            ious = iou_matrix(det_boxes[list(det_indices)], track_boxes)
            # Greedy best-first IoU matching (small N in traffic scenes).
            order = np.dstack(np.unravel_index(np.argsort(-ious.ravel()), ious.shape))[0]
            local_used, track_used = set(), set()
            for di, ti in order:
                if ious[di, ti] < self.iou_threshold:
                    break
                det_i = list(det_indices)[di]
                candidate = dets[det_i]
                track = self._tracks[ti]
                if (candidate.class_name != track.cls or
                        (candidate.camera_id and track.camera_id and candidate.camera_id != track.camera_id)):
                    continue
                if di in local_used or ti in track_used:
                    continue
                local_used.add(di)
                track_used.add(ti)
                det_i = list(det_indices)[di]
                tr = self._tracks[ti]
                d = dets[det_i]
                tr.kf.update(d.bbox)
                tr.observed_bbox = list(d.bbox)
                tr.cls = d.class_name
                tr.conf = float(d.confidence)
                tr.hits += 1
                tr.since_update_ms = 0.0
                tr.last_pts = pts_ms if pts_ms is not None else tr.last_pts
                if d.camera_id:
                    tr.camera_id = d.camera_id
                matched_ids.add(tr.track_id)
                matched_det_idx.add(det_i)

        # 2) ByteTrack two-stage association.
        high_idx = [i for i, d in enumerate(dets) if d.confidence >= self.high_conf]
        low_idx = [i for i, d in enumerate(dets) if self.low_conf <= d.confidence < self.high_conf]
        associate(high_idx)
        remaining_tracks = [i for i, t in enumerate(self._tracks) if t.track_id not in matched_ids]
        if low_idx and remaining_tracks:
            # Associate low-conf detections with still-unmatched tracks only.
            saved = self._tracks
            self._tracks = [saved[i] for i in remaining_tracks]
            associate(low_idx)
            self._tracks = saved

        # 3) Birth: unmatched detections become tentative tracks.
        for i, d in enumerate(dets):
            if i in matched_det_idx:
                continue
            if len(self._tracks) >= self.max_tracks:
                # Real new observations take priority over lost predictions.
                # Never let ghosts fill the capacity and suppress photo crops.
                lost = [track for track in self._tracks if track.since_update_ms > 0]
                if not lost:
                    continue
                self._tracks.remove(max(lost, key=lambda track: track.since_update_ms))
            self._tracks.append(
                _TrackState(self._new_id(), d.bbox, d.class_name, float(d.confidence), pts_ms, d.camera_id)
            )

        # 4) Death: tracks silent longer than max_age (PTS-based).
        self._tracks = [t for t in self._tracks if t.since_update_ms <= self.max_age_ms]

        if pts_ms is not None:
            self._last_pts = pts_ms

        # 5) Confirmed tracks only.
        out: List[Track] = []
        for t in self._tracks:
            if t.hits >= self.min_hits or self.min_hits <= 1:
                out.append(
                    Track(
                        track_id=t.track_id,
                        bbox=t.kf.bbox(),
                        class_name=t.cls,
                        confidence=t.conf,
                        camera_id=t.camera_id,
                        first_pts_ms=t.first_pts,
                        last_pts_ms=t.last_pts,
                        hits=t.hits,
                        frames=t.frames,
                        time_since_update_ms=t.since_update_ms,
                        observed_bbox=list(t.observed_bbox),
                    )
                )
        return out

    # ------------------------------------------------------------------
    def lost_tracks(self, pts_ms: Optional[float] = None) -> List[Track]:
        """Tracks currently unmatched this frame (for event-on-loss logic)."""
        out = []
        for t in self._tracks:
            if t.since_update_ms > 0:
                out.append(
                    Track(
                        track_id=t.track_id,
                        bbox=t.kf.bbox(),
                        class_name=t.cls,
                        confidence=t.conf,
                        camera_id=t.camera_id,
                        first_pts_ms=t.first_pts,
                        last_pts_ms=t.last_pts,
                        hits=t.hits,
                        frames=t.frames,
                        time_since_update_ms=t.since_update_ms,
                        observed_bbox=list(t.observed_bbox),
                    )
                )
        return out

    def active_count(self) -> int:
        return len(self._tracks)
