"""
Lightweight multi-vehicle tracker for uploaded CCTV videos.

Greedy IoU association between consecutive detection frames with a small
miss-tolerance so tracks survive brief occlusions and detector flicker.
Dependency-free (pure Python + the detector's boxes) and fast enough for
hackathon-scale offline video processing.

Each track keeps a stable integer id within one video processing run:
vehicles entering the view get a new id, vehicles leaving are retired, and
close/overlapping vehicles keep separate ids while their boxes differ.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass
class TrackedBox:
    track_id: int
    x1: int
    y1: int
    x2: int
    y2: int
    class_name: str
    confidence: float
    hits: int = 1
    misses: int = 0


def _iou(a: Sequence[float], b: Sequence[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = ix2 - ix1, iy2 - iy1
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    area_a = max(ax2 - ax1, 0.0) * max(ay2 - ay1, 0.0)
    area_b = max(bx2 - bx1, 0.0) * max(by2 - by1, 0.0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class SimpleTracker:
    """Greedy IoU tracker. One instance per video processing run."""

    def __init__(self, iou_threshold: float = 0.25, max_misses: int = 8) -> None:
        self.iou_threshold = iou_threshold
        self.max_misses = max_misses
        self._next_id = 1
        self._tracks: Dict[int, TrackedBox] = {}

    @property
    def tracks(self) -> List[TrackedBox]:
        return list(self._tracks.values())

    def update(
        self,
        detections: List[Tuple[int, int, int, int, str, float]],
    ) -> Tuple[List[TrackedBox], List[TrackedBox]]:
        """
        Match new detections to live tracks.

        Returns (matched_or_new_tracks, retired_tracks). Retired tracks are
        removed from the live set — the caller should flush their ANPR state.
        """
        det_boxes = [(d[0], d[1], d[2], d[3]) for d in detections]
        track_ids = list(self._tracks.keys())

        # Greedy best-IoU matching (highest IoU pairs first).
        pairs: List[Tuple[float, int, int]] = []
        for ti, tid in enumerate(track_ids):
            t = self._tracks[tid]
            for di, box in enumerate(det_boxes):
                pairs.append((_iou((t.x1, t.y1, t.x2, t.y2), box), ti, di))
        pairs.sort(key=lambda p: p[0], reverse=True)

        matched_tracks: Dict[int, int] = {}  # track index -> detection index
        matched_dets: Dict[int, int] = {}    # detection index -> track index
        for score, ti, di in pairs:
            if score < self.iou_threshold:
                break
            if ti in matched_tracks or di in matched_dets:
                continue
            matched_tracks[ti] = di
            matched_dets[di] = ti

        live: List[TrackedBox] = []
        for ti, tid in enumerate(track_ids):
            track = self._tracks[tid]
            if ti in matched_tracks:
                x1, y1, x2, y2, cls, conf = detections[matched_tracks[ti]]
                track.x1, track.y1, track.x2, track.y2 = x1, y1, x2, y2
                track.class_name = cls
                track.confidence = conf
                track.hits += 1
                track.misses = 0
            else:
                track.misses += 1
            live.append(track)

        # New tracks for unmatched detections.
        for di, det in enumerate(detections):
            if di in matched_dets:
                continue
            x1, y1, x2, y2, cls, conf = det
            track = TrackedBox(
                track_id=self._next_id,
                x1=x1, y1=y1, x2=x2, y2=y2,
                class_name=cls, confidence=conf,
            )
            self._next_id += 1
            live.append(track)

        # Retire stale tracks.
        kept: Dict[int, TrackedBox] = {}
        retired: List[TrackedBox] = []
        for track in live:
            if track.misses > self.max_misses:
                retired.append(track)
            else:
                kept[track.track_id] = track
        self._tracks = kept
        return list(kept.values()), retired

    def flush(self) -> List[TrackedBox]:
        """Retire every live track (end of video)."""
        retired = list(self._tracks.values())
        self._tracks = {}
        return retired

    def get(self, track_id: int) -> Optional[TrackedBox]:
        return self._tracks.get(track_id)
