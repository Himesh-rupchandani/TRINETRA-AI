"""
CV-layer event deduplication (spec §19).

Key = (camera_id, track_id, plate). Within a configurable suppression window
one sighting event is emitted; afterwards the same vehicle may legitimately
re-emit (e.g. it stayed on screen for minutes and the track is still alive —
see EVENT_MAX_TRACK_HOLD_SEC handling in the pipeline).

Different cameras are NEVER suppressed against each other: the key includes
camera_id, so cam04 and cam08 both produce their own sightings.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

DedupKey = Tuple[str, int, str]  # camera_id, track_id, plate ("" for plateless)


class SightingDeduplicator:
    def __init__(self, suppression_sec: float = 30.0):
        self.suppression_ms = suppression_sec * 1000.0
        self._last_emit: Dict[DedupKey, float] = {}
        self.suppressed_count = 0
        self.emitted_count = 0

    def _key(self, camera_id: str, track_id: int, plate: Optional[str]) -> DedupKey:
        return (camera_id, int(track_id), (plate or "").upper())

    def should_emit(self, camera_id: str, track_id: int, plate: Optional[str], pts_ms: float) -> bool:
        """Return True (and record emission) unless suppressed by the window."""
        key = self._key(camera_id, track_id, plate)
        last = self._last_emit.get(key)
        if last is not None and (pts_ms - last) < self.suppression_ms:
            self.suppressed_count += 1
            return False
        self._last_emit[key] = pts_ms
        self.emitted_count += 1
        return True

    def forget_track(self, camera_id: str, track_id: int) -> None:
        """Remove history for a finished track (memory hygiene)."""
        for key in [k for k in self._last_emit if k[0] == camera_id and k[1] == track_id]:
            self._last_emit.pop(key, None)

    def reset(self) -> None:
        self._last_emit.clear()

    def stats(self) -> dict:
        return {"emitted": self.emitted_count, "suppressed": self.suppressed_count}
