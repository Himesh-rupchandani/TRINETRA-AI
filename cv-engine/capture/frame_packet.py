"""
FramePacket — the unit of data moving from capture into the CV pipeline.

Timing contract (spec §10):
- `pts_ms` is the PRIMARY video timing source (container presentation time).
- `received_at` is wall-clock arrival time for diagnostics ONLY. It must never
  be used for tracking, dwell time, speed or any temporal reasoning.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import numpy as np


class CaptureState(str, Enum):
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    STOPPED = "STOPPED"


@dataclass
class FramePacket:
    """A decoded frame with authoritative PTS timing and capture context."""

    frame: np.ndarray
    camera_id: str
    pts_ms: float
    capture_state: CaptureState = CaptureState.ONLINE
    sequence_number: int = 0
    is_discontinuity: bool = False
    source_type: str = "rtsp"  # rtsp | hls | file | demo
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def elapsed_ms_since(self, previous: Optional["FramePacket"]) -> Optional[float]:
        """PTS delta vs a previous packet. None if unknown/non-monotonic context."""
        if previous is None:
            return None
        return self.pts_ms - previous.pts_ms

    def __repr__(self) -> str:  # keep logs short
        h, w = self.frame.shape[:2] if self.frame is not None else (0, 0)
        return (
            f"FramePacket(cam={self.camera_id}, seq={self.sequence_number}, "
            f"pts={self.pts_ms:.1f}ms, {w}x{h}, disc={self.is_discontinuity}, "
            f"src={self.source_type})"
        )
