"""
Per-track multi-frame plate accumulation (spec §18, §19).

A tracked vehicle is read across many frames; readings are collected here and
aggregated into ONE stable candidate per track. The pipeline emits at most
one (or a few) sighting events per track — never one event per frame.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .confidence import PlateReading, aggregate_readings, classify_confidence, is_usable


@dataclass
class TrackPlateState:
    """Accumulated plate evidence for one (camera, track) pair."""

    readings: List[PlateReading] = field(default_factory=list)
    last_emitted_key: Optional[str] = None   # f"{plate}" of last emitted event
    last_emitted_pts_ms: Optional[float] = None
    emitted_count: int = 0

    def add_reading(self, reading: PlateReading, reject_threshold: float, format_discount: float = 0.0) -> None:
        """Store a reading unless it is rejected by confidence or format."""
        if not reading.plate_normalized:
            return
        tier = classify_confidence(reading.confidence, reject_threshold=reject_threshold)
        if not is_usable(tier):
            return
        self.readings.append(reading)

    def best(self) -> Optional[dict]:
        """
        Current stable candidate or None.
        Returns {plate, confidence, plate_raw, n_readings}.
        """
        agg = aggregate_readings(self.readings)
        if agg is None:
            return None
        plate, conf, raw = agg
        return {"plate": plate, "confidence": conf, "plate_raw": raw, "n_readings": len(self.readings)}

    def is_stable(self, min_agree_reads: int) -> bool:
        """True when >= min_agree_reads readings agree on the winning plate."""
        agg = aggregate_readings(self.readings)
        if agg is None:
            return False
        plate, _, _ = agg
        agree = sum(1 for r in self.readings if r.plate_normalized == plate)
        return agree >= min_agree_reads


class PlateMemory:
    """Manages TrackPlateState per track_id for one camera. Reset on scene cut."""

    def __init__(self, camera_id: str, reject_threshold: float = 0.60, min_agree_reads: int = 2):
        self.camera_id = camera_id
        self.reject_threshold = reject_threshold
        self.min_agree_reads = min_agree_reads
        self._states: Dict[int, TrackPlateState] = {}

    def state_for(self, track_id: int) -> TrackPlateState:
        if track_id not in self._states:
            self._states[track_id] = TrackPlateState()
        return self._states[track_id]

    def add_reading(self, track_id: int, reading: PlateReading) -> None:
        self.state_for(track_id).add_reading(reading, self.reject_threshold)

    def best(self, track_id: int) -> Optional[dict]:
        st = self._states.get(track_id)
        return st.best() if st else None

    def is_stable(self, track_id: int) -> bool:
        st = self._states.get(track_id)
        return st.is_stable(self.min_agree_reads) if st else False

    def drop(self, track_id: int) -> None:
        self._states.pop(track_id, None)

    def reset(self) -> None:
        """Scene discontinuity: every track identity is invalid now (spec §14)."""
        self._states.clear()

    def track_ids(self) -> List[int]:
        return list(self._states.keys())
