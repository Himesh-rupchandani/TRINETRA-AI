"""Event de-duplication at the CV layer.

A tracked vehicle is visible for many frames; the backend must receive *one*
meaningful sighting, not 500 near-identical ones. The key is ``(camera, track,
plate)`` and the window is ``dedup_window_s`` (PTS seconds), so the *same*
vehicle re-appearing on the *same* camera later than the window produces a new
sighting, and a *different* camera always produces its own sighting.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from logging_setup import log_event

log = logging.getLogger("trinetra.events.dedup")


class EventDeduplicator:
    """Temporal suppression of near-identical sightings. Thread-safe."""

    def __init__(self, window_s: float = 45.0, unplated_window_s: float = 20.0) -> None:
        self.window_ms = float(window_s) * 1000.0
        self.unplated_window_ms = float(unplated_window_s) * 1000.0
        self._last: dict[tuple, float] = {}
        self._lock = threading.Lock()
        self.suppressed = 0
        self.emitted = 0

    def key(self, camera_id: str, track_id: Optional[int], plate: str) -> tuple:
        return (str(camera_id).lower(), track_id, (plate or "").upper())

    def should_emit(self, camera_id: str, track_id: Optional[int], plate: str, continuous_ms: float) -> bool:
        """True when this sighting is new enough to be sent to the backend."""
        key = self.key(camera_id, track_id, plate)
        window = self.window_ms if plate else self.unplated_window_ms
        with self._lock:
            last = self._last.get(key)
            if last is not None and (continuous_ms - last) < window:
                self.suppressed += 1
                log_event(
                    log,
                    "event_suppressed",
                    level=logging.DEBUG,
                    camera=camera_id,
                    track_id=track_id,
                    plate=plate or "-",
                    since_s=(continuous_ms - last) / 1000.0,
                )
                return False
            self._last[key] = continuous_ms
            self.emitted += 1
        return True

    def reset(self) -> None:
        with self._lock:
            self._last.clear()

    def prune(self, continuous_ms: float, max_age_ms: float = 3600_000.0) -> int:
        """Drop keys older than ``max_age_ms`` so a long run does not leak memory."""
        with self._lock:
            stale = [k for k, ts in self._last.items() if (continuous_ms - ts) > max_age_ms]
            for k in stale:
                del self._last[k]
        return len(stale)
