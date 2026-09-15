from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from ..core.vision import np


class CameraState(str, Enum):
    """Explicit camera lifecycle states conforming to Mandatory Rule 10."""
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    STOPPED = "STOPPED"

@dataclass
class FramePacket:
    """
    Standardized CCTV Frame Ingestion Packet conforming to Mandatory Rules 3, 11, 12, 14.
    
    Fields:
    - frame: Video frame as a NumPy array (BGR format).
    - pts_ms: Video presentation timestamp in milliseconds extracted from stream container.
              MUST be the primary video timing source (NOT arrival time / constant FPS).
    - camera_id: Identifier of the source camera (e.g. 'CAM04').
    - sequence_number: Monotonically increasing frame index per stream session.
    - received_at: Wall-clock UTC timestamp when frame arrived in ingestion worker
                   (diagnostic/monitoring only - not for physics/velocity timing).
    - is_discontinuity: True if a scene cut, stream loop, PTS jump, or reconnect occurred,
                        signaling AI trackers (e.g. ByteTrack) to reset active tracks.
    - source_type: Origin type ('rtsp', 'hls', 'file', 'demo').
    """
    frame: np.ndarray
    pts_ms: float
    camera_id: str
    sequence_number: int
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_discontinuity: bool = False
    source_type: str = "rtsp"

    def __repr__(self) -> str:
        h, w = self.frame.shape[:2] if self.frame is not None else (0, 0)
        return (
            f"FramePacket(cam={self.camera_id}, seq={self.sequence_number}, "
            f"pts={self.pts_ms:.1f}ms, shape=({w}x{h}), "
            f"discontinuity={self.is_discontinuity}, src={self.source_type})"
        )
