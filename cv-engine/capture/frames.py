"""Frame packets and PTS handling.

Timing rule (Sentinel guidance, and the single most important rule in this
engine):

* The **PTS carried by the stream** is the only video clock. ``pts_ms`` below is
  that value.
* ``datetime.now()`` is recorded as ``arrived_at`` for *operational* logging and
  event wall-clock stamps only. It is never used for speed, dwell time or
  inter-frame deltas.
* ``CAP_PROP_FPS`` is not trusted: government feeds routinely misreport it, and
  the decoder drops frames anyway.

Sentinel feeds also **loop**, so raw PTS is not guaranteed monotonic across a
scene restart. :class:`PtsTimeline` therefore keeps the raw PTS *and* a
monotonic ``continuous_ms`` that survives loops; the tracker consumes the
continuous value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np

# Capture states surfaced on every packet (and in metrics/logs).
STATE_OK = "OK"
STATE_RECOVERED = "RECOVERED"
STATE_STALLED = "STALLED"
STATE_ERROR = "ERROR"
STATE_CLOSED = "CLOSED"

#: Floor for the PTS rewind tolerance. The effective tolerance is
#: ``max(this, 1.5 * nominal frame interval)``: small enough that a genuine
#: rewind (a looping feed restarting) is always caught, large enough to absorb
#: sub-frame PTS jitter without falsely declaring a scene cut.
PTS_BACKWARD_TOLERANCE_MS = 1.0
#: A forward jump larger than this is a discontinuity, not a real gap.
PTS_FORWARD_JUMP_MS = 10_000.0


@dataclass
class FramePacket:
    """One decoded frame plus everything the pipeline needs to reason about it."""

    frame: np.ndarray
    camera_id: str
    pts_ms: float
    capture_state: str = STATE_OK
    source: str = "rtsp"  # rtsp | hls | file | synthetic
    seq: int = 0
    arrived_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    decode_ms: float = 0.0
    #: Monotonic PTS corrected for stream loops. Use this for all durations.
    continuous_ms: float = 0.0
    pts_valid: bool = True
    scene_cut: bool = False

    @property
    def width(self) -> int:
        return int(self.frame.shape[1]) if self.frame is not None else 0

    @property
    def height(self) -> int:
        return int(self.frame.shape[0]) if self.frame is not None else 0

    @property
    def wall_clock_iso(self) -> str:
        """UTC ISO-8601 with a Z suffix — the ``event_time`` field of an event."""
        return self.arrived_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PtsTimeline:
    """Turns a possibly-discontinuous raw PTS stream into usable timing.

    Handles three real-world conditions on Sentinel feeds:

    1. **Looping** — PTS jumps backwards when the feed restarts. The epoch is
       incremented so ``continuous_ms`` keeps increasing.
    2. **Missing/unavailable PTS** — some decoders report 0 or ``nan``. We then
       fall back to a nominal interval, and mark ``pts_valid=False`` so
       downstream code can avoid deriving speed from a guessed clock.
    3. **Long stalls** — a forward jump far beyond the nominal interval is
       reported as a discontinuity so the tracker can drop stale tracks.
    """

    def __init__(self, nominal_interval_ms: float = 40.0) -> None:
        self.nominal_interval_ms = max(float(nominal_interval_ms), 1.0)
        self._epoch_offset_ms = 0.0
        self._last_raw: Optional[float] = None
        self._last_continuous: Optional[float] = None
        self._expected_next: Optional[float] = None
        self.loops = 0
        self.invalid_count = 0

    def reset(self, nominal_interval_ms: float | None = None) -> None:
        if nominal_interval_ms:
            self.nominal_interval_ms = max(float(nominal_interval_ms), 1.0)
        self._epoch_offset_ms = 0.0
        self._last_raw = None
        self._last_continuous = None
        self._expected_next = None

    def update(self, raw_pts_ms: float | None) -> tuple[float, float, bool, bool]:
        """Ingest one raw PTS.

        Returns ``(continuous_ms, delta_ms, pts_valid, discontinuity)``.
        """
        valid = raw_pts_ms is not None and _is_finite(raw_pts_ms) and raw_pts_ms >= 0
        discontinuity = False

        if not valid:
            self.invalid_count += 1
            delta = self.nominal_interval_ms if self._last_continuous is not None else 0.0
            continuous = (self._last_continuous or 0.0) + delta
            self._last_continuous = continuous
            # Raw PTS is unknown; keep the continuous clock alive but flag it.
            return continuous, delta, False, False

        raw = float(raw_pts_ms)
        if self._last_raw is None:
            continuous = raw
            delta = 0.0
        else:
            delta_raw = raw - self._last_raw
            rewind_tolerance = max(PTS_BACKWARD_TOLERANCE_MS, 1.5 * self.nominal_interval_ms)
            if delta_raw < -rewind_tolerance:
                # Stream restarted / looped: shift the epoch forward.
                self.loops += 1
                self._epoch_offset_ms += self._last_raw + self.nominal_interval_ms
                discontinuity = True
                delta = self.nominal_interval_ms
            elif delta_raw > PTS_FORWARD_JUMP_MS:
                discontinuity = True
                delta = delta_raw
            else:
                delta = max(delta_raw, 0.0)
            continuous = raw + self._epoch_offset_ms

        self._last_raw = raw
        self._last_continuous = continuous
        self._expected_next = raw + self.nominal_interval_ms
        return continuous, delta, True, discontinuity

    @property
    def last_continuous_ms(self) -> float:
        return self._last_continuous or 0.0


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


def nominal_interval_from_fps(fps: float | None, default_ms: float = 40.0) -> float:
    """Nominal frame interval in ms.

    The catalogue FPS is a *hint* used only to size the fallback interval when
    PTS is unavailable. It is never used as the timing source.
    """
    if fps and fps > 0:
        return 1000.0 / float(fps)
    return default_ms
