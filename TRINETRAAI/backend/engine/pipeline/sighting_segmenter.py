"""
Sighting segmenter (Phase 5/6 of Faculty Parking pipeline).

CORE DISTINCTION:
    FRAME  — a single decoded image from the video
    TRACK  — a continuous ID assigned by ByteTrack while a vehicle stays visible
    SIGHTING — one logical appearance of a vehicle in the scene

RULES:
    Many frames → one track → one sighting (while continuously visible).
    Vehicle leaves scene → track ends → if same vehicle returns → NEW sighting.
    A sighting is "closed" when its track has been lost for >= TRACK_END_GAP_SECONDS.

This module does NOT do detection or tracking — it sits DOWNSTREAM of the tracker
and groups track lifetimes + plate readings into sighting events.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import cv2

logger = logging.getLogger("cv_engine.sighting")


@dataclass
class FrameEvidence:
    """Atomic evidence data for one frame within a sighting."""
    frame_index: int
    pts_ms: float
    bbox: List[float]
    confidence: float
    vehicle_class: str
    track_id: int = -1
    plate_text: Optional[str] = None
    plate_raw: Optional[str] = None
    plate_confidence: Optional[float] = None
    plate_bbox: Optional[List[float]] = None
    frame_image: Optional[np.ndarray] = None
    vehicle_crop: Optional[np.ndarray] = None
    plate_crop: Optional[np.ndarray] = None
    # Quality metrics for representative frame selection
    bbox_area: float = 0.0
    sharpness: float = 0.0
    has_plate: bool = False


@dataclass
class Sighting:
    """One logical appearance of a vehicle in the scene."""
    sighting_id: int
    track_ids: List[int] = field(default_factory=list)
    first_frame_index: int = 0
    last_frame_index: int = 0
    first_pts_ms: float = 0.0
    last_pts_ms: float = 0.0
    vehicle_class: str = "vehicle"
    # Plate OCR candidates across frames (for multi-frame voting)
    plate_candidates: List[Tuple[str, float]] = field(default_factory=list)
    # Aggregated result
    final_plate: Optional[str] = None
    final_plate_raw: Optional[str] = None
    plate_confidence: float = 0.0
    supporting_frame_count: int = 0
    # Representative evidence frame & assets (all guaranteed from the exact same frame)
    best_frame: Optional[FrameEvidence] = None
    best_frame_image: Optional[np.ndarray] = None
    best_vehicle_crop: Optional[np.ndarray] = None
    best_plate_crop: Optional[np.ndarray] = None
    representative_frame_index: int = 0
    representative_pts_ms: float = 0.0
    representative_ocr_confidence: float = 0.0
    representative_vehicle_bbox: Optional[List[float]] = None
    representative_plate_bbox: Optional[List[float]] = None
    # Candidate pool for selecting the true representative frame
    _candidate_evidences: List[FrameEvidence] = field(default_factory=list)
    _best_vehicle_only_evidence: Optional[FrameEvidence] = None
    # All frame counts
    frame_count: int = 0
    detection_count: int = 0
    # State
    is_closed: bool = False
    closed_at_pts_ms: Optional[float] = None

    @property
    def duration_sec(self) -> float:
        return max(0.0, (self.last_pts_ms - self.first_pts_ms) / 1000.0)

    @property
    def timestamp_str(self) -> str:
        total_sec = self.first_pts_ms / 1000.0
        minutes = int(total_sec // 60)
        seconds = total_sec % 60
        return f"{minutes:02d}:{seconds:05.2f}"

    def to_dict(self) -> dict:
        v_conf = round(self.best_frame.confidence, 4) if self.best_frame else 0.0
        v_bbox = self.representative_vehicle_bbox or (self.best_frame.bbox if self.best_frame else None)
        p_bbox = self.representative_plate_bbox or (self.best_frame.plate_bbox if self.best_frame else None)
        return {
            "sighting_id": self.sighting_id,
            "track_ids": self.track_ids,
            "first_frame_index": self.first_frame_index,
            "last_frame_index": self.last_frame_index,
            "representative_frame_index": self.representative_frame_index,
            "representative_pts_ms": self.representative_pts_ms,
            "first_pts_ms": self.first_pts_ms,
            "last_pts_ms": self.last_pts_ms,
            "duration_sec": round(self.duration_sec, 2),
            "timestamp": self.timestamp_str,
            "vehicle_class": self.vehicle_class,
            "vehicle_confidence": v_conf,
            "vehicle_bbox": v_bbox,
            "plate_bbox": p_bbox,
            "final_plate": self.final_plate,
            "final_plate_raw": self.final_plate_raw,
            "plate_confidence": round(self.plate_confidence, 4),
            "supporting_frame_count": self.supporting_frame_count,
            "frame_count": self.frame_count,
            "detection_count": self.detection_count,
            "is_closed": self.is_closed,
        }


def _compute_sharpness(image: np.ndarray) -> float:
    """Laplacian variance as a sharpness proxy."""
    if image is None or image.size == 0:
        return 0.0
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception:
        return 0.0


def _bbox_area(bbox: List[float]) -> float:
    if len(bbox) < 4:
        return 0.0
    return max(0.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))


class SightingSegmenter:
    """
    Groups track lifetimes into distinct vehicle sightings.

    Usage:
        segmenter = SightingSegmenter()
        for each frame:
            segmenter.update(frame_index, pts_ms, tracks, plate_readings, frame)
        segmenter.finalize()
        sightings = segmenter.get_all_sightings()
    """

    def __init__(
        self,
        track_end_gap_seconds: float = 3.0,
        sighting_cooldown_seconds: float = 5.0,
        min_sighting_frames: int = 3,
        min_sighting_duration_sec: float = 0.5,
    ):
        self.track_end_gap_sec = track_end_gap_seconds
        self.sighting_cooldown_sec = sighting_cooldown_seconds
        self.min_sighting_frames = min_sighting_frames
        self.min_sighting_duration_sec = min_sighting_duration_sec

        self._next_sighting_id = 1
        # track_id -> current open sighting
        self._active_sightings: Dict[int, Sighting] = {}
        # track_id -> last seen PTS
        self._track_last_seen_pts: Dict[int, float] = {}
        # All completed sightings
        self._completed_sightings: List[Sighting] = []

    def _new_sighting_id(self) -> int:
        sid = self._next_sighting_id
        self._next_sighting_id += 1
        return sid

    def update(
        self,
        frame_index: int,
        pts_ms: float,
        active_track_ids: List[int],
        track_data: Dict[int, dict],  # {track_id: {bbox, class, confidence}}
        plate_readings: Dict[int, Tuple[Optional[str], Optional[str], float]],  # {track_id: (raw, norm, conf)}
        frame: Optional[np.ndarray] = None,
        plate_crops: Optional[Dict[int, np.ndarray]] = None,
        plate_bboxes: Optional[Dict[int, List[float]]] = None,
    ) -> None:
        """
        Process one frame's worth of tracking + plate data.
        Creates atomic FrameEvidence where full frame, vehicle crop, plate crop,
        and plate reading originate strictly from this single frame.
        """
        gap_ms = self.track_end_gap_sec * 1000.0

        # 1) Check for tracks that have gone silent → close their sightings
        lost_track_ids = []
        for tid, last_pts in list(self._track_last_seen_pts.items()):
            if tid not in active_track_ids:
                if (pts_ms - last_pts) >= gap_ms:
                    lost_track_ids.append(tid)

        for tid in lost_track_ids:
            if tid in self._active_sightings:
                sighting = self._active_sightings.pop(tid)
                self._close_sighting(sighting, pts_ms)
            self._track_last_seen_pts.pop(tid, None)

        # 2) Update active tracks
        for tid in active_track_ids:
            data = track_data.get(tid, {})
            bbox = data.get("bbox", [0, 0, 0, 0])
            cls = data.get("class_name", "vehicle")
            conf = data.get("confidence", 0.0)

            # Is this track already part of an open sighting?
            if tid in self._active_sightings:
                sighting = self._active_sightings[tid]
            else:
                # New track → new sighting
                sighting = Sighting(
                    sighting_id=self._new_sighting_id(),
                    track_ids=[tid],
                    first_frame_index=frame_index,
                    first_pts_ms=pts_ms,
                    vehicle_class=cls,
                )
                self._active_sightings[tid] = sighting

            # Update sighting state
            sighting.last_frame_index = frame_index
            sighting.last_pts_ms = pts_ms
            sighting.frame_count += 1
            sighting.detection_count += 1

            # Plate reading on this exact frame?
            has_plate = False
            p_raw, p_norm, p_conf = None, None, 0.0
            p_crop, p_bbox = None, None

            if tid in plate_readings:
                p_raw, p_norm, p_conf = plate_readings[tid]
                if p_norm and p_conf > 0.0:
                    sighting.plate_candidates.append((p_norm, p_conf))
                    has_plate = True

            if plate_crops and tid in plate_crops:
                c = plate_crops[tid]
                if c is not None and c.size > 0:
                    p_crop = c.copy()
                    has_plate = True

            if plate_bboxes and tid in plate_bboxes:
                p_bbox = list(plate_bboxes[tid])

            # Atomic vehicle crop from this exact frame with contextual padding
            v_crop = _safe_crop(frame, bbox, padding_ratio=0.08) if frame is not None else None
            sharpness = _compute_sharpness(v_crop) if v_crop is not None else 0.0
            area = _bbox_area(bbox)

            evidence = FrameEvidence(
                frame_index=frame_index,
                pts_ms=pts_ms,
                bbox=list(bbox),
                confidence=conf,
                vehicle_class=cls,
                track_id=tid,
                plate_text=p_norm,
                plate_raw=p_raw,
                plate_confidence=p_conf,
                plate_bbox=p_bbox,
                frame_image=frame.copy() if frame is not None else None,
                vehicle_crop=v_crop,
                plate_crop=p_crop,
                bbox_area=area,
                sharpness=sharpness,
                has_plate=has_plate and (p_crop is not None and p_crop.size > 0),
            )

            # Keep candidate pool
            if evidence.has_plate:
                sighting._candidate_evidences.append(evidence)
                # Keep top 12 candidate frames sorted by plate evidence quality
                if len(sighting._candidate_evidences) > 12:
                    sighting._candidate_evidences.sort(key=_plate_evidence_score, reverse=True)
                    for discarded in sighting._candidate_evidences[12:]:
                        discarded.frame_image = None
                        discarded.vehicle_crop = None
                        discarded.plate_crop = None
                    sighting._candidate_evidences = sighting._candidate_evidences[:12]
            else:
                # Track best vehicle-only frame
                if (sighting._best_vehicle_only_evidence is None or
                        _frame_quality_score(evidence) > _frame_quality_score(sighting._best_vehicle_only_evidence)):
                    sighting._best_vehicle_only_evidence = evidence

            # Fallback initial best_frame
            if sighting.best_frame is None:
                sighting.best_frame = evidence
                sighting.best_frame_image = evidence.frame_image
                sighting.best_vehicle_crop = evidence.vehicle_crop
                sighting.best_plate_crop = evidence.plate_crop
                sighting.representative_frame_index = evidence.frame_index
                sighting.representative_pts_ms = evidence.pts_ms
                sighting.representative_vehicle_bbox = evidence.bbox
                sighting.representative_plate_bbox = evidence.plate_bbox

            self._track_last_seen_pts[tid] = pts_ms

    def _close_sighting(self, sighting: Sighting, pts_ms: float) -> None:
        """Finalize a sighting: aggregate plates, select authoritative representative frame, check minimums, store."""
        sighting.is_closed = True
        sighting.closed_at_pts_ms = pts_ms

        # 1) Aggregate plate candidates (multi-frame voting)
        self._aggregate_plates(sighting)

        # 2) Authoritative Representative Frame Selection
        # ROOT RULE: ONE DETECTION = ONE EVIDENCE OBJECT
        # full_frame + vehicle_crop + plate_crop MUST all come from the SAME frame.
        selected_evidence: Optional[FrameEvidence] = None

        if sighting._candidate_evidences:
            # Priority 1: Candidates where plate_text matches final_plate exactly and plate crop is valid
            if sighting.final_plate:
                matching = [
                    c for c in sighting._candidate_evidences
                    if c.has_plate and c.plate_text == sighting.final_plate
                    and c.plate_crop is not None and c.plate_crop.size > 0
                    and c.frame_image is not None
                ]
                if matching:
                    selected_evidence = max(matching, key=_plate_evidence_score)
            
            # Priority 2: Candidates that have a valid plate crop and frame image
            if selected_evidence is None:
                with_plate = [
                    c for c in sighting._candidate_evidences
                    if c.has_plate and c.plate_crop is not None and c.plate_crop.size > 0
                    and c.frame_image is not None
                ]
                if with_plate:
                    selected_evidence = max(with_plate, key=_plate_evidence_score)

        # Priority 3: No valid plate candidate -> use best vehicle-only evidence
        if selected_evidence is None:
            selected_evidence = sighting._best_vehicle_only_evidence or sighting.best_frame

        if selected_evidence is not None:
            sighting.best_frame = selected_evidence
            sighting.best_frame_image = selected_evidence.frame_image
            if selected_evidence.vehicle_crop is not None:
                sighting.best_vehicle_crop = selected_evidence.vehicle_crop
            elif selected_evidence.frame_image is not None:
                sighting.best_vehicle_crop = _safe_crop(selected_evidence.frame_image, selected_evidence.bbox, padding_ratio=0.08)
            else:
                sighting.best_vehicle_crop = None

            # Plate crop strictly from this exact representative frame
            if selected_evidence.plate_crop is not None and selected_evidence.plate_crop.size > 0:
                sighting.best_plate_crop = selected_evidence.plate_crop
            elif selected_evidence.plate_bbox and selected_evidence.frame_image is not None:
                sighting.best_plate_crop = _safe_crop(selected_evidence.frame_image, selected_evidence.plate_bbox, padding_ratio=0.06)
            else:
                sighting.best_plate_crop = None
            sighting.representative_frame_index = selected_evidence.frame_index
            sighting.representative_pts_ms = selected_evidence.pts_ms
            sighting.representative_ocr_confidence = (
                selected_evidence.plate_confidence if selected_evidence.has_plate else 0.0
            )
            sighting.representative_vehicle_bbox = list(selected_evidence.bbox)
            sighting.representative_plate_bbox = (
                list(selected_evidence.plate_bbox) if selected_evidence.plate_bbox else None
            )

        # Free candidate image memory
        sighting._candidate_evidences.clear()
        sighting._best_vehicle_only_evidence = None

        # Only keep sightings that meet minimum thresholds
        if (sighting.frame_count >= self.min_sighting_frames
                and sighting.duration_sec >= self.min_sighting_duration_sec):
            self._completed_sightings.append(sighting)
            logger.info(
                "Sighting #%d closed: plate=%s conf=%.2f rep_frame=%d rep_pts=%.1fms frames=%d duration=%.1fs",
                sighting.sighting_id, sighting.final_plate,
                sighting.plate_confidence, sighting.representative_frame_index,
                sighting.representative_pts_ms, sighting.frame_count,
                sighting.duration_sec,
            )
        else:
            logger.debug(
                "Sighting #%d discarded (too short: %d frames, %.1fs)",
                sighting.sighting_id, sighting.frame_count, sighting.duration_sec,
            )

    def _aggregate_plates(self, sighting: Sighting) -> None:
        """Multi-frame OCR voting: pick the most consistent plate reading."""
        if not sighting.plate_candidates:
            sighting.final_plate = None
            sighting.plate_confidence = 0.0
            sighting.supporting_frame_count = 0
            return

        # Group by normalized plate text
        clusters: Dict[str, List[float]] = {}
        for plate, conf in sighting.plate_candidates:
            clusters.setdefault(plate, []).append(conf)

        # Pick winning cluster by (count, mean_confidence)
        def cluster_score(item):
            plate, confs = item
            return (len(confs), sum(confs) / len(confs))

        best_plate, best_confs = max(clusters.items(), key=cluster_score)

        # Aggregate confidence: 0.5 * max + 0.5 * mean (same as confidence.py)
        agg_conf = 0.5 * max(best_confs) + 0.5 * (sum(best_confs) / len(best_confs))

        sighting.final_plate = best_plate
        sighting.plate_confidence = min(agg_conf, 1.0)
        sighting.supporting_frame_count = len(best_confs)

        # Find the best raw reading for this plate
        for raw_plate, conf in sighting.plate_candidates:
            if raw_plate == best_plate:
                sighting.final_plate_raw = raw_plate
                break

    def finalize(self) -> None:
        """Close all remaining open sightings (end of video)."""
        for tid, sighting in list(self._active_sightings.items()):
            last_pts = self._track_last_seen_pts.get(tid, sighting.last_pts_ms)
            self._close_sighting(sighting, last_pts)
        self._active_sightings.clear()
        self._track_last_seen_pts.clear()

    def get_all_sightings(self) -> List[Sighting]:
        """Return all completed sightings, sorted by first_pts_ms."""
        return sorted(self._completed_sightings, key=lambda s: s.first_pts_ms)

    def get_sightings_by_plate(self, fuzzy: bool = True) -> Dict[str, List[Sighting]]:
        """
        Group sightings by their final normalized plate.
        If fuzzy=True, merge plates with edit distance <= 1 into the canonical plate.
        """
        raw_grouped: Dict[str, List[Sighting]] = {}
        for s in self.get_all_sightings():
            plate = s.final_plate or "UNKNOWN"
            raw_grouped.setdefault(plate, []).append(s)

        if not fuzzy:
            return raw_grouped

        # Fuzzy clustering for known plates
        known_plates = [p for p in raw_grouped.keys() if p != "UNKNOWN"]
        # Sort by cluster size descending, then confidence
        known_plates.sort(
            key=lambda p: (
                len(raw_grouped[p]),
                sum(s.plate_confidence for s in raw_grouped[p]) / len(raw_grouped[p]),
            ),
            reverse=True,
        )

        canonical_map: Dict[str, str] = {}
        for p in known_plates:
            if p in canonical_map:
                continue
            canonical_map[p] = p
            for other in known_plates:
                if other in canonical_map:
                    continue
                # Substring match (handles missing state prefix e.g. EL8933 in GJ03EL8933)
                if len(other) >= 5 and len(p) >= 6 and (other in p or p in other):
                    canonical_map[other] = p
                    logger.info("Substring-merged plate %s into canonical %s", other, p)
                    continue

                # If length >= 6 and edit distance <= 1, cluster together
                if len(p) >= 6 and len(other) >= 6 and abs(len(p) - len(other)) <= 1:
                    if levenshtein_distance(p, other) <= 1:
                        canonical_map[other] = p
                        logger.info("Fuzzy-merged plate %s into canonical %s", other, p)

        # Merge groups
        merged: Dict[str, List[Sighting]] = {}
        if "UNKNOWN" in raw_grouped:
            merged["UNKNOWN"] = raw_grouped["UNKNOWN"]

        for plate, sightings in raw_grouped.items():
            if plate == "UNKNOWN":
                continue
            canonical = canonical_map.get(plate, plate)
            merged.setdefault(canonical, []).extend(sightings)

        # Re-sort each list by first_pts_ms
        for p in merged:
            merged[p].sort(key=lambda s: s.first_pts_ms)

        return merged

    def get_plate_summary(self, fuzzy: bool = True) -> List[dict]:
        """Summary: unique plates and sighting counts."""
        by_plate = self.get_sightings_by_plate(fuzzy=fuzzy)
        summary = []
        for plate, sightings in sorted(by_plate.items(), key=lambda x: -len(x[1])):
            summary.append({
                "plate": plate,
                "sighting_count": len(sightings),
                "avg_confidence": round(
                    sum(s.plate_confidence for s in sightings) / len(sightings), 4
                ) if sightings else 0.0,
                "timestamps": [s.timestamp_str for s in sightings],
            })
        return summary

    def find_target_vehicle(self, expected_sightings: int = 5) -> Optional[dict]:
        """
        Find the vehicle with exactly `expected_sightings` distinct sightings.
        Tries fuzzy grouping first, then exact. If none found exactly, returns closest.
        """
        for use_fuzzy in (True, False):
            by_plate = self.get_sightings_by_plate(fuzzy=use_fuzzy)
            known_plates = {p: s for p, s in by_plate.items() if p != "UNKNOWN"}

            if not known_plates:
                continue

            for plate, sightings in known_plates.items():
                if len(sightings) == expected_sightings:
                    return {
                        "plate": plate,
                        "sighting_count": len(sightings),
                        "exact_match": True,
                        "sightings": sightings,
                    }

        # Fallback to closest match
        by_plate = self.get_sightings_by_plate(fuzzy=True)
        known_plates = {p: s for p, s in by_plate.items() if p != "UNKNOWN"}
        if not known_plates:
            return None

        closest_plate = min(
            known_plates.keys(),
            key=lambda p: abs(len(known_plates[p]) - expected_sightings),
        )
        return {
            "plate": closest_plate,
            "sighting_count": len(known_plates[closest_plate]),
            "exact_match": False,
            "sightings": known_plates[closest_plate],
        }


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _safe_crop(frame: np.ndarray, bbox, padding_ratio: float = 0.0) -> Optional[np.ndarray]:
    """Safely crop a region from a frame with optional contextual padding."""
    try:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = [float(v) for v in bbox]
        bw = x2 - x1
        bh = y2 - y1
        if bw < 4 or bh < 4:
            return None

        if padding_ratio > 0.0:
            pad_x = bw * padding_ratio
            pad_y = bh * padding_ratio
            x1 = x1 - pad_x
            y1 = y1 - pad_y
            x2 = x2 + pad_x
            y2 = y2 + pad_y

        x1 = max(0.0, x1)
        y1 = max(0.0, y1)
        x2 = min(float(w), x2)
        y2 = min(float(h), y2)

        ix1, iy1 = int(round(x1)), int(round(y1))
        ix2, iy2 = int(round(x2)), int(round(y2))
        if ix2 - ix1 < 6 or iy2 - iy1 < 6:
            return None
        return frame[iy1:iy2, ix1:ix2]
    except Exception:
        return None


def _frame_quality_score(evidence: Optional[FrameEvidence]) -> float:
    """Score a frame for best-frame selection."""
    if evidence is None:
        return -1.0
    score = 0.0
    # Larger vehicle bbox = better visibility (normalized roughly)
    score += min(evidence.bbox_area / 50000.0, 2.0)
    # Sharper = better
    score += min(evidence.sharpness / 500.0, 1.0)
    # Detection confidence
    score += evidence.confidence
    # Plate detected and confident = big bonus
    if evidence.plate_text and evidence.plate_confidence:
        score += evidence.plate_confidence * 2.0
    return score


def _plate_evidence_score(ev: Optional[FrameEvidence]) -> float:
    """Score a frame specifically for plate evidence quality."""
    if ev is None:
        return 0.0
    return float(ev.plate_confidence or 0.0) + (float(ev.confidence or 0.0) * 0.1)
