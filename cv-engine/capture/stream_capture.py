"""
Stream capture base (spec §8, §10, §14).

- Video timing comes from container PTS (CAP_PROP_POS_MSEC), never from
  wall-clock arrival time and never from frame_number / CAP_PROP_FPS.
- CAP_PROP_FPS is NOT trusted for timing (diagnostic only).
- Inter-frame gaps are normal; transient decode failures do not immediately
  kill the stream.
- Scene discontinuities (feed loops, hard cuts, reconnects) are flagged on the
  FramePacket so downstream tracking can reset.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import cv2
import numpy as np

from .frame_packet import CaptureState, FramePacket

logger = logging.getLogger("cv_engine.capture")

# Discontinuity thresholds (ms)
PTS_ROLLBACK_MS = 500.0     # PTS moved backwards -> stream loop / reset
PTS_GAP_MS = 5000.0         # PTS jumped forward -> stream gap
MAX_CONSECUTIVE_FAILS = 15  # sustained read failures -> needs reconnect
DEGRADED_AFTER_FAILS = 3


class StreamCaptureBase:
    """Common capture logic over an OpenCV/FFmpeg VideoCapture."""

    source_type = "stream"

    def __init__(
        self,
        camera_id: str,
        url: str,
        read_timeout_sec: float = 6.0,
        scene_cut_check: bool = True,
        scene_cut_diff_threshold: float = 42.0,
    ):
        self.camera_id = camera_id
        self.url = url
        self.read_timeout_sec = read_timeout_sec
        self.scene_cut_check = scene_cut_check
        self.scene_cut_diff_threshold = scene_cut_diff_threshold

        self.cap: Optional[cv2.VideoCapture] = None
        self.state = CaptureState.OFFLINE
        self.last_error: Optional[str] = None

        self._sequence = 0
        self._frame_count = 0
        self._reads_since_open = 0
        self._last_pts_ms: Optional[float] = None
        self._pts_base_mono: float = 0.0  # for monotonic fallback clock
        self._pos_msec_reliable = False   # has CAP_PROP_POS_MSEC ever reported > 0?
        self._just_connected = False
        self._consecutive_failures = 0
        self._last_ok_mono = 0.0
        self._prev_thumb: Optional[np.ndarray] = None
        self._opened_mono = 0.0

    # -- connection -----------------------------------------------------------
    def _capture_kwargs(self) -> dict:
        """Override in subclasses to set protocol-specific FFmpeg options."""
        return {}

    def open(self) -> bool:
        self.state = CaptureState.CONNECTING
        self.last_error = None
        self.close_capture_object()

        try:
            kwargs = self._capture_kwargs()
            if kwargs:
                self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG, kwargs)
            else:
                self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        except Exception as exc:
            self.state = CaptureState.OFFLINE
            self.last_error = f"capture open raised: {exc}"
            logger.warning("[%s] %s", self.camera_id, self.last_error)
            return False

        if self.cap is None or not self.cap.isOpened():
            self.state = CaptureState.OFFLINE
            self.last_error = f"cannot open {self.source_type.upper()} stream: {self.url}"
            logger.warning("[%s] %s", self.camera_id, self.last_error)
            return False

        # Validate by reading one frame (some sources 'open' but never decode).
        ok, frame = self._guarded_read()
        if not ok or frame is None:
            self.state = CaptureState.OFFLINE
            self.last_error = "stream opened but initial frame read failed"
            logger.warning("[%s] %s", self.camera_id, self.last_error)
            self.close_capture_object()
            return False

        now = time.monotonic()
        self.state = CaptureState.ONLINE
        self._just_connected = True
        self._consecutive_failures = 0
        self._last_ok_mono = now
        self._opened_mono = now
        self._pts_base_mono = now
        self._last_pts_ms = None
        self._pos_msec_reliable = False
        self._reads_since_open = 1  # validation frame
        self._prev_thumb = None
        logger.info("[%s] %s connected: %s", self.camera_id, self.source_type.upper(), self.url)
        return True

    def close_capture_object(self) -> None:
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def close(self) -> None:
        self.close_capture_object()
        self.state = CaptureState.STOPPED

    # -- PTS --------------------------------------------------------------------
    def _extract_pts_ms(self) -> float:
        """
        Primary: container PTS via CAP_PROP_POS_MSEC.

        Availability handling (documented):
        - POS_MSEC > 0          -> container PTS, trusted from then on.
        - POS_MSEC == 0 early   -> legitimate first-frame timestamp, return 0.
        - POS_MSEC == 0 forever -> muxer does not expose PTS; after a few
          reads we switch to a monotonic stream clock (connection-relative).
        The fallback is still stream-derived timing — never frame arrival
        jitter, never CAP_PROP_FPS arithmetic.
        """
        pos = -1.0
        if self.cap is not None:
            try:
                pos = self.cap.get(cv2.CAP_PROP_POS_MSEC)
            except Exception:
                pos = -1.0
        if pos is not None and pos > 0.0:
            self._pos_msec_reliable = True
            return float(pos)
        if pos is not None and pos == 0.0:
            if self._pos_msec_reliable:
                return 0.0
            if self._reads_since_open < 3:
                return 0.0  # PTS 0 is a legal container timestamp early on
            # source has never exposed PTS — monotonic fallback clock
        return (time.monotonic() - self._pts_base_mono) * 1000.0

    # -- discontinuity --------------------------------------------------------------
    def _detect_discontinuity(self, pts_ms: float, frame: np.ndarray) -> bool:
        if self._just_connected:
            self._just_connected = False
            logger.info("[%s] discontinuity: first frame after (re)connect", self.camera_id)
            return True

        if self._last_pts_ms is not None:
            if pts_ms < self._last_pts_ms - PTS_ROLLBACK_MS:
                logger.warning(
                    "[%s] discontinuity: PTS rollback %.1f -> %.1f ms (feed loop?)",
                    self.camera_id, self._last_pts_ms, pts_ms,
                )
                return True
            if pts_ms - self._last_pts_ms > PTS_GAP_MS:
                logger.warning(
                    "[%s] discontinuity: PTS gap %.1f ms",
                    self.camera_id, pts_ms - self._last_pts_ms,
                )
                return True

        if self.scene_cut_check:
            thumb = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (64, 36))
            if self._prev_thumb is not None:
                diff = float(np.mean(cv2.absdiff(thumb, self._prev_thumb)))
                if diff > self.scene_cut_diff_threshold:
                    logger.warning(
                        "[%s] discontinuity: hard scene cut (diff=%.1f)", self.camera_id, diff
                    )
                    self._prev_thumb = thumb
                    return True
            self._prev_thumb = thumb
        return False

    # -- reading --------------------------------------------------------------
    def _guarded_read(self):
        try:
            return self.cap.read()
        except Exception as exc:
            logger.warning("[%s] cap.read() raised: %s", self.camera_id, exc)
            return False, None

    def read_packet(self) -> Optional[FramePacket]:
        """
        Read one frame -> FramePacket with PTS. Returns None when no frame is
        currently available (transient) — caller decides when to reconnect.
        """
        if self.cap is None or not self.cap.isOpened():
            self.state = CaptureState.OFFLINE
            return None

        now = time.monotonic()
        ok, frame = self._guarded_read()

        if ok and frame is not None and getattr(frame, "size", 0) > 0:
            self._consecutive_failures = 0
            self._last_ok_mono = now
            self._frame_count += 1
            self._sequence += 1
            self._reads_since_open += 1
            self.state = CaptureState.ONLINE

            pts_ms = self._extract_pts_ms()
            is_disc = self._detect_discontinuity(pts_ms, frame)
            self._last_pts_ms = pts_ms

            return FramePacket(
                frame=frame,
                camera_id=self.camera_id,
                pts_ms=pts_ms,
                capture_state=self.state,
                sequence_number=self._sequence,
                is_discontinuity=is_disc,
                source_type=self.source_type,
            )

        # Transient decode failure handling (spec: gaps are normal)
        self._consecutive_failures += 1
        since_ok = now - self._last_ok_mono
        if (
            self._consecutive_failures >= MAX_CONSECUTIVE_FAILS
            or since_ok > self.read_timeout_sec
        ):
            self.state = CaptureState.RECONNECTING
            self.last_error = (
                f"sustained read failure ({self._consecutive_failures} fails, "
                f"{since_ok:.1f}s since last frame)"
            )
            logger.warning("[%s] %s", self.camera_id, self.last_error)
        elif self._consecutive_failures >= DEGRADED_AFTER_FAILS and self.state != CaptureState.DEGRADED:
            self.state = CaptureState.DEGRADED
            logger.warning(
                "[%s] degraded: %d consecutive empty reads",
                self.camera_id, self._consecutive_failures,
            )
        return None

    def needs_reconnect(self) -> bool:
        return self.state in (CaptureState.RECONNECTING, CaptureState.OFFLINE)

    # -- diagnostics ------------------------------------------------------------
    @property
    def frame_count(self) -> int:
        return self._frame_count

    def diagnostics(self) -> dict:
        nominal_fps = None
        if self.cap is not None:
            try:
                nominal_fps = self.cap.get(cv2.CAP_PROP_FPS)  # diagnostic only
            except Exception:
                nominal_fps = None
        return {
            "camera_id": self.camera_id,
            "state": self.state.value,
            "frames": self._frame_count,
            "last_pts_ms": self._last_pts_ms,
            "nominal_fps_reported_by_container": nominal_fps,  # NOT used for timing
            "last_error": self.last_error,
        }
