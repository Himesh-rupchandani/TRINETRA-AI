"""
Sighting segmentation — FRAME vs TRACK vs SIGHTING (spec §5, §6 of the
Faculty-Parking brief).

The distinction this module exists to enforce:

    a vehicle visible for 8 seconds  ->  ~200 frames
                                     ->  1 track (ideally)
                                     ->  1 SIGHTING

A new sighting is only created when a vehicle's track has been *gone* for a
meaningful gap and the vehicle later comes back. Two independent mechanisms
cooperate:

1. ``track_end_gap_sec`` — an open sighting is closed once its track has not
   been observed for that long (the tracker itself may keep coasting a lost
   track for a shorter max-age).
2. ``sighting_cooldown_sec`` — after closing, if the SAME normalized plate
   re-appears within the cooldown it is merged back into the previous
   sighting. This absorbs tracker ID-switches (occlusion, a pillar, a passing
   vehicle) which would otherwise inflate the sighting count.

Nothing here fabricates data: plates come from multi-frame OCR voting
(``anpr.confidence.aggregate_readings``) and a sighting with no readable plate
is reported as such.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from anpr.confidence import PlateReading, aggregate_readings

logger = logging.getLogger("cv_engine.sightings")

PLATE_DETECTED = "DETECTED"
PLATE_UNCERTAIN = "UNCERTAIN"
PLATE_NOT_DETECTED = "NOT_DETECTED"


@dataclass
class PlateObservation:
    """One OCR read of one plate crop belonging to one track."""

    pts_ms: float
    frame_index: int
    plate_raw: str
    plate_normalized: str
    ocr_confidence: float
    plate_det_confidence: float = 0.0
    plate_bbox: Optional[List[float]] = None
    plate_area_px: float = 0.0
    sharpness: float = 0.0
    quality: float = 0.0

    def to_reading(self) -> PlateReading:
        return PlateReading(
            plate_raw=self.plate_raw,
            plate_normalized=self.plate_normalized,
            confidence=self.ocr_confidence,
            pts_ms=self.pts_ms,
        )

    def to_dict(self) -> dict:
        return {
            "pts_ms": round(self.pts_ms, 1),
            "timestamp_sec": round(self.pts_ms / 1000.0, 3),
            "frame_index": self.frame_index,
            "plate_raw": self.plate_raw,
            "plate": self.plate_normalized,
            "ocr_confidence": round(self.ocr_confidence, 4),
            "plate_det_confidence": round(self.plate_det_confidence, 4),
            "plate_bbox": [round(float(v), 1) for v in self.plate_bbox] if self.plate_bbox else None,
            "plate_area_px": round(self.plate_area_px, 1),
            "sharpness": round(self.sharpness, 2),
            "quality": round(self.quality, 4),
        }


@dataclass
class Evidence:
    """Best evidence frame + plate crop for a sighting (kept in memory until written)."""

    frame: Optional[np.ndarray] = None
    plate_crop: Optional[np.ndarray] = None
    pts_ms: float = 0.0
    frame_index: int = -1
    quality: float = -1.0
    vehicle_bbox: Optional[List[float]] = None
    plate_bbox: Optional[List[float]] = None
    ocr_confidence: float = 0.0
    frame_ref: Optional[str] = None       # filled by the writer
    plate_crop_ref: Optional[str] = None  # filled by the writer


@dataclass
class Sighting:
    """One distinct appearance of one vehicle at one camera/video."""

    camera_id: str
    video_id: str
    track_ids: List[int] = field(default_factory=list)
    vehicle_class: str = "car"
    class_votes: Dict[str, int] = field(default_factory=dict)
    start_pts_ms: float = 0.0
    end_pts_ms: float = 0.0
    first_frame_index: int = -1
    last_frame_index: int = -1
    frames_observed: int = 0
    detection_confidences: List[float] = field(default_factory=list)
    plate_observations: List[PlateObservation] = field(default_factory=list)
    evidence: Evidence = field(default_factory=Evidence)
    sighting_id: Optional[str] = None
    sighting_index_for_plate: Optional[int] = None
    merged_from: int = 1  # how many raw track-sessions were merged into this

    # ------------------------------------------------------------ derived
    @property
    def duration_sec(self) -> float:
        return max(0.0, (self.end_pts_ms - self.start_pts_ms) / 1000.0)

    @property
    def track_id(self) -> int:
        return self.track_ids[0] if self.track_ids else -1

    @property
    def mean_detection_confidence(self) -> float:
        if not self.detection_confidences:
            return 0.0
        return float(sum(self.detection_confidences) / len(self.detection_confidences))

    def dominant_class(self) -> str:
        if not self.class_votes:
            return self.vehicle_class
        return max(self.class_votes.items(), key=lambda kv: kv[1])[0]

    def plate_result(
        self, reject_threshold: float = 0.60, min_agree_reads: int = 2
    ) -> Tuple[Optional[str], Optional[str], Optional[float], int, str]:
        """
        Multi-frame OCR voting for this sighting (spec §10 of the brief).

        Returns ``(plate, plate_raw, confidence, supporting_frame_count, status)``.
        The winning candidate is the one supported by the most agreeing reads
        (ties broken by mean confidence) — never simply the first read.
        """
        if not self.plate_observations:
            return None, None, None, 0, PLATE_NOT_DETECTED

        agg = aggregate_readings([o.to_reading() for o in self.plate_observations])
        if agg is None:
            return None, None, None, 0, PLATE_NOT_DETECTED
        plate, conf, raw = agg
        support = sum(1 for o in self.plate_observations if o.plate_normalized == plate)

        status = PLATE_DETECTED
        if conf < reject_threshold or support < min_agree_reads:
            status = PLATE_UNCERTAIN
        return plate, raw, conf, support, status

    def candidate_summary(self) -> List[dict]:
        """All competing OCR candidates with their support — full transparency."""
        buckets: Dict[str, List[PlateObservation]] = {}
        for o in self.plate_observations:
            buckets.setdefault(o.plate_normalized, []).append(o)
        out = []
        for plate, obs in buckets.items():
            confs = [o.ocr_confidence for o in obs]
            out.append({
                "plate": plate,
                "reads": len(obs),
                "max_ocr_confidence": round(max(confs), 4),
                "mean_ocr_confidence": round(sum(confs) / len(confs), 4),
            })
        out.sort(key=lambda d: (-d["reads"], -d["mean_ocr_confidence"]))
        return out


class SightingSegmenter:
    """
    Turns per-frame track observations into distinct sighting events.

    Parameters
    ----------
    track_end_gap_sec
        Close an open sighting when its track has been unobserved this long.
    sighting_cooldown_sec
        Re-appearance of the same plate within this gap is treated as the SAME
        sighting (tracker ID-switch absorption), not a new one.
    min_frames / min_duration_sec
        Spurious one-or-two-frame tracks are dropped (false-positive control).
    """

    def __init__(
        self,
        camera_id: str,
        video_id: str,
        track_end_gap_sec: float = 2.0,
        sighting_cooldown_sec: float = 3.0,
        min_frames: int = 3,
        min_duration_sec: float = 0.3,
        reject_threshold: float = 0.60,
        min_agree_reads: int = 2,
        keep_evidence_frames: bool = True,
    ):
        self.camera_id = camera_id
        self.video_id = video_id
        self.track_end_gap_sec = float(track_end_gap_sec)
        self.sighting_cooldown_sec = float(sighting_cooldown_sec)
        self.min_frames = int(min_frames)
        self.min_duration_sec = float(min_duration_sec)
        self.reject_threshold = float(reject_threshold)
        self.min_agree_reads = int(min_agree_reads)
        self.keep_evidence_frames = keep_evidence_frames

        self._open: Dict[int, Sighting] = {}
        self._last_seen_pts: Dict[int, float] = {}
        self.closed: List[Sighting] = []
        self.dropped_short = 0

    # ------------------------------------------------------------------
    def observe_track(
        self,
        track_id: int,
        pts_ms: float,
        frame_index: int,
        vehicle_class: str,
        detection_confidence: float,
        bbox: Sequence[float],
    ) -> None:
        """Record that ``track_id`` was seen in this frame."""
        s = self._open.get(track_id)
        if s is None:
            s = Sighting(
                camera_id=self.camera_id,
                video_id=self.video_id,
                track_ids=[track_id],
                vehicle_class=vehicle_class,
                start_pts_ms=pts_ms,
                first_frame_index=frame_index,
            )
            self._open[track_id] = s
        s.end_pts_ms = pts_ms
        s.last_frame_index = frame_index
        s.frames_observed += 1
        s.detection_confidences.append(float(detection_confidence))
        s.class_votes[vehicle_class] = s.class_votes.get(vehicle_class, 0) + 1
        self._last_seen_pts[track_id] = pts_ms

    def add_plate_observation(
        self,
        track_id: int,
        observation: PlateObservation,
        frame: Optional[np.ndarray] = None,
        plate_crop: Optional[np.ndarray] = None,
        vehicle_bbox: Optional[Sequence[float]] = None,
    ) -> None:
        """
        Attach one OCR read to the OPEN sighting of ``track_id``.

        Plate text can only ever be attached to the track it was cropped from
        (spec §20: no cross-vehicle plate leakage).
        """
        s = self._open.get(track_id)
        if s is None:
            return
        s.plate_observations.append(observation)
        if observation.quality > s.evidence.quality:
            s.evidence = Evidence(
                frame=frame.copy() if (frame is not None and self.keep_evidence_frames) else None,
                plate_crop=plate_crop.copy() if plate_crop is not None else None,
                pts_ms=observation.pts_ms,
                frame_index=observation.frame_index,
                quality=observation.quality,
                vehicle_bbox=[float(v) for v in vehicle_bbox] if vehicle_bbox is not None else None,
                plate_bbox=observation.plate_bbox,
                ocr_confidence=observation.ocr_confidence,
            )

    def offer_plateless_evidence(
        self,
        track_id: int,
        frame: Optional[np.ndarray],
        pts_ms: float,
        frame_index: int,
        vehicle_bbox: Sequence[float],
        quality: float,
    ) -> None:
        """
        Keep a best-frame even for vehicles whose plate never resolves, so a
        NOT_DETECTED sighting still ships verifiable evidence.
        """
        s = self._open.get(track_id)
        if s is None or s.plate_observations:
            return
        if quality > s.evidence.quality:
            s.evidence = Evidence(
                frame=frame.copy() if (frame is not None and self.keep_evidence_frames) else None,
                plate_crop=None,
                pts_ms=pts_ms,
                frame_index=frame_index,
                quality=quality,
                vehicle_bbox=[float(v) for v in vehicle_bbox],
            )

    # ------------------------------------------------------------------
    def tick(self, pts_ms: float) -> List[Sighting]:
        """Close sightings whose track has been gone for ``track_end_gap_sec``."""
        gap_ms = self.track_end_gap_sec * 1000.0
        expired = [
            tid for tid, last in self._last_seen_pts.items()
            if tid in self._open and (pts_ms - last) > gap_ms
        ]
        return [s for tid in expired if (s := self._close(tid)) is not None]

    def close_all(self) -> List[Sighting]:
        return [s for tid in list(self._open.keys()) if (s := self._close(tid)) is not None]

    def _close(self, track_id: int) -> Optional[Sighting]:
        s = self._open.pop(track_id, None)
        self._last_seen_pts.pop(track_id, None)
        if s is None:
            return None
        if s.frames_observed < self.min_frames or s.duration_sec < self.min_duration_sec:
            # Too short to be a real appearance: a flicker detection, not a sighting.
            self.dropped_short += 1
            logger.debug(
                "[SIGHTING] dropped short track %s (%d frames, %.2fs)",
                track_id, s.frames_observed, s.duration_sec,
            )
            return None
        s.vehicle_class = s.dominant_class()
        self.closed.append(s)
        return s

    # ------------------------------------------------------------------
    def finalize(self) -> List[Sighting]:
        """
        Close everything, merge ID-switch fragments, and assign stable ids.

        Merging rule: same normalized plate AND the next fragment starts within
        ``sighting_cooldown_sec`` of the previous fragment's end.
        """
        self.close_all()
        raw = sorted(self.closed, key=lambda s: s.start_pts_ms)
        merged: List[Sighting] = []
        by_plate_last: Dict[str, Sighting] = {}

        for s in raw:
            plate, _, _, _, status = s.plate_result(self.reject_threshold, self.min_agree_reads)
            key = plate if (plate and status == PLATE_DETECTED) else None
            if key is not None:
                prev = by_plate_last.get(key)
                # A negative gap means the two fragments OVERLAP in time: the
                # tracker held two boxes for one physical vehicle. A plate is
                # unique to a vehicle, so that is a duplicate to suppress, not
                # a second sighting.
                if prev is not None and (s.start_pts_ms - prev.end_pts_ms) <= self.sighting_cooldown_sec * 1000.0:
                    # Same vehicle, same visit — the tracker just changed its id.
                    prev.end_pts_ms = max(prev.end_pts_ms, s.end_pts_ms)
                    prev.last_frame_index = max(prev.last_frame_index, s.last_frame_index)
                    prev.frames_observed += s.frames_observed
                    prev.detection_confidences.extend(s.detection_confidences)
                    prev.plate_observations.extend(s.plate_observations)
                    prev.track_ids.extend(t for t in s.track_ids if t not in prev.track_ids)
                    prev.merged_from += 1
                    for c, n in s.class_votes.items():
                        prev.class_votes[c] = prev.class_votes.get(c, 0) + n
                    prev.vehicle_class = prev.dominant_class()
                    if s.evidence.quality > prev.evidence.quality:
                        prev.evidence = s.evidence
                    logger.info(
                        "[SIGHTING] merged track %s into earlier sighting of %s (gap %.2fs)",
                        s.track_ids, key, (s.start_pts_ms - prev.end_pts_ms) / 1000.0,
                    )
                    continue
                by_plate_last[key] = s
            merged.append(s)

        # Stable ids + per-plate sighting numbering.
        counters: Dict[str, int] = {}
        for i, s in enumerate(sorted(merged, key=lambda x: x.start_pts_ms), start=1):
            plate, _, _, _, status = s.plate_result(self.reject_threshold, self.min_agree_reads)
            key = plate if (plate and status == PLATE_DETECTED) else "UNKNOWN"
            counters[key] = counters.get(key, 0) + 1
            s.sighting_index_for_plate = counters[key]
            s.sighting_id = f"sighting_{i:03d}"
        return sorted(merged, key=lambda x: x.start_pts_ms)
