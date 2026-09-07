"""
Video-FILE capture source (offline analysis of uploaded/recorded footage).

This complements the live RTSP/HLS capture classes: the same ``FramePacket``
contract is produced, so every downstream stage (detector, tracker, ANPR,
events, evidence) is reused unchanged for recorded video.

Timing contract (spec §10): ``pts_ms`` comes from the container
(``CAP_PROP_POS_MSEC``). When the container reports a non-monotonic or zero
PTS — common for phone recordings with variable frame interval — we fall back
to ``frame_index / fps``, and we always report which timing source was used
instead of silently guessing.

Robustness (spec: one bad frame must not kill the analysis):
- a failed ``read()`` is retried up to ``max_decode_failures`` times before the
  stream is considered finished,
- decode gaps are counted and exposed in :attr:`VideoFileSource.stats`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import cv2

from .frame_packet import CaptureState, FramePacket

logger = logging.getLogger("cv_engine.capture.file")


@dataclass
class VideoProbe:
    """Measured (never assumed) properties of a video file."""

    path: str
    opened: bool
    width: int = 0
    height: int = 0
    fps_reported: float = 0.0
    frame_count_reported: int = 0
    duration_sec_reported: float = 0.0
    fourcc: str = ""
    # Filled by measure_actual_fps()
    fps_measured: Optional[float] = None
    duration_sec_measured: Optional[float] = None
    frames_decoded_in_probe: int = 0
    pts_monotonic: Optional[bool] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "opened": self.opened,
            "resolution": f"{self.width}x{self.height}",
            "width": self.width,
            "height": self.height,
            "fps_reported": round(self.fps_reported, 4),
            "fps_measured": round(self.fps_measured, 4) if self.fps_measured else None,
            "frame_count_reported": self.frame_count_reported,
            "duration_sec_reported": round(self.duration_sec_reported, 3),
            "duration_sec_measured": (
                round(self.duration_sec_measured, 3) if self.duration_sec_measured else None
            ),
            "fourcc": self.fourcc,
            "pts_monotonic": self.pts_monotonic,
            "frames_decoded_in_probe": self.frames_decoded_in_probe,
            "error": self.error,
        }


def _fourcc_str(value: float) -> str:
    try:
        v = int(value)
    except Exception:
        return ""
    if v <= 0:
        return ""
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4)).strip()


def probe_video(path: str, measure_frames: int = 0) -> VideoProbe:
    """
    Open ``path`` and report its REAL properties.

    ``measure_frames`` > 0 additionally decodes that many frames to measure the
    delivered FPS from PTS (container metadata is often wrong for phone/CCTV
    recordings) and to verify frames actually decode.
    """
    p = VideoProbe(path=str(path), opened=False)
    if not Path(path).exists():
        p.error = "file not found"
        return p

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        p.error = "cv2.VideoCapture could not open the file"
        return p

    p.opened = True
    p.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    p.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    p.fps_reported = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    p.frame_count_reported = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    p.fourcc = _fourcc_str(cap.get(cv2.CAP_PROP_FOURCC))
    if p.fps_reported > 0 and p.frame_count_reported > 0:
        p.duration_sec_reported = p.frame_count_reported / p.fps_reported

    if measure_frames > 0:
        pts_values = []
        decoded = 0
        monotonic = True
        last = -1.0
        while decoded < measure_frames:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            decoded += 1
            pts = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
            pts_values.append(pts)
            if pts < last:
                monotonic = False
            last = pts
        p.frames_decoded_in_probe = decoded
        p.pts_monotonic = monotonic if decoded > 1 else None
        if decoded > 1 and pts_values[-1] > pts_values[0]:
            span_sec = (pts_values[-1] - pts_values[0]) / 1000.0
            p.fps_measured = (decoded - 1) / span_sec if span_sec > 0 else None

    # Duration measured from the last decodable PTS (accurate even when the
    # frame-count header lies).
    if p.frame_count_reported > 0:
        cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 1.0)
        end_ms = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
        if end_ms > 0:
            p.duration_sec_measured = end_ms / 1000.0

    cap.release()
    return p


@dataclass
class FileSourceStats:
    frames_read: int = 0
    frames_yielded: int = 0
    decode_failures: int = 0
    non_monotonic_pts: int = 0
    synthetic_pts_frames: int = 0
    first_pts_ms: Optional[float] = None
    last_pts_ms: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "frames_read": self.frames_read,
            "frames_yielded": self.frames_yielded,
            "decode_failures": self.decode_failures,
            "non_monotonic_pts": self.non_monotonic_pts,
            "synthetic_pts_frames": self.synthetic_pts_frames,
            "first_pts_ms": self.first_pts_ms,
            "last_pts_ms": self.last_pts_ms,
        }


class VideoFileSource:
    """
    Iterate a video file as ``FramePacket``s.

    Parameters
    ----------
    path
        Video file.
    camera_id
        Logical camera/video id stamped on every packet.
    frame_skip
        Yield every Nth decoded frame (1 = every frame). Frames are always
        DECODED sequentially (seeking per-frame is slower and less reliable);
        only inference-bound frames are yielded.
    start_sec / duration_sec
        Optional analysis window (used by the short "sample mode" run).
    max_decode_failures
        Consecutive failed reads tolerated before the source stops.
    """

    def __init__(
        self,
        path: str,
        camera_id: str = "video",
        frame_skip: int = 1,
        start_sec: float = 0.0,
        duration_sec: Optional[float] = None,
        max_decode_failures: int = 30,
    ):
        self.path = str(path)
        self.camera_id = camera_id
        self.frame_skip = max(1, int(frame_skip))
        self.start_sec = max(0.0, float(start_sec))
        self.duration_sec = duration_sec
        self.max_decode_failures = max(1, int(max_decode_failures))
        self.stats = FileSourceStats()
        self.probe: Optional[VideoProbe] = None
        self._fps_fallback = 25.0

    # ------------------------------------------------------------------
    def open(self) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(self.path)
        if not cap.isOpened():
            raise IOError(f"cannot open video: {self.path}")
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if fps > 0:
            self._fps_fallback = fps
        if self.start_sec > 0:
            cap.set(cv2.CAP_PROP_POS_MSEC, self.start_sec * 1000.0)
        return cap

    def frames(self) -> Iterator[FramePacket]:
        """Yield FramePackets. Never raises on a single bad frame."""
        cap = self.open()
        frame_index = -1
        consecutive_failures = 0
        last_pts = -1.0
        emitted = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    consecutive_failures += 1
                    self.stats.decode_failures += 1
                    if consecutive_failures >= self.max_decode_failures:
                        break
                    continue
                consecutive_failures = 0
                frame_index += 1
                self.stats.frames_read += 1

                pts_ms = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
                synthetic = False
                if pts_ms <= 0.0 and frame_index > 0:
                    # Container PTS unavailable → derive from index & fps.
                    pts_ms = (frame_index / self._fps_fallback) * 1000.0
                    synthetic = True
                    self.stats.synthetic_pts_frames += 1
                if pts_ms < last_pts:
                    self.stats.non_monotonic_pts += 1
                    # Keep timing monotonic for the tracker; never rewind.
                    pts_ms = last_pts + (1000.0 / self._fps_fallback)
                    synthetic = True

                if self.duration_sec is not None:
                    if pts_ms / 1000.0 > self.start_sec + self.duration_sec:
                        break

                last_pts = pts_ms
                if self.stats.first_pts_ms is None:
                    self.stats.first_pts_ms = pts_ms
                self.stats.last_pts_ms = pts_ms

                if frame_index % self.frame_skip != 0:
                    continue

                emitted += 1
                self.stats.frames_yielded += 1
                yield FramePacket(
                    frame=frame,
                    camera_id=self.camera_id,
                    pts_ms=pts_ms,
                    capture_state=CaptureState.ONLINE,
                    sequence_number=frame_index,
                    is_discontinuity=False,
                    source_type="file",
                )
        finally:
            cap.release()
            if self.stats.decode_failures:
                logger.warning(
                    "[FILE] %s: %d decode failure(s) tolerated, %d frames read",
                    self.path, self.stats.decode_failures, self.stats.frames_read,
                )
