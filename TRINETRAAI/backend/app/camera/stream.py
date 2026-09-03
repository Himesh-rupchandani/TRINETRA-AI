import os
import sys
from pathlib import Path
import time
import threading
from typing import Tuple, Optional
from datetime import datetime, timezone
import numpy as np
import cv2

# Allow running this file directly as a script
if __name__ == "__main__" and not __package__:
    project_root = Path(__file__).resolve().parents[3]
    backend_root = Path(__file__).resolve().parents[2]
    for p in [str(project_root), str(backend_root)]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    __package__ = "backend.app.camera"

from ..core.config import settings
from ..core.logging_config import logger
from ..utils.timestamps import utc_now
from .packet import FramePacket, CameraState
from .reconnect import StreamReconnectHandler


class CameraStream:
    """
    Production-grade CCTV Stream Ingestion Engine conforming to Mandatory Rules 1 - 14.
    
    Key Features:
    - Rule 1: Forces RTSP over TCP via OPENCV_FFMPEG_CAPTURE_OPTIONS and supports HLS fallback.
    - Rule 2 & 3: PTS-driven timing via cv2.CAP_PROP_POS_MSEC (never assumes constant FPS).
    - Rule 4 & 6: Tolerates irregular frame delivery and transient decoder warnings (DEGRADED state).
    - Rule 5: Exponential backoff reconnection (2s -> 4s -> 8s -> 16s -> 30s max).
    - Rule 7: Scene discontinuity detector (PTS rollback/jump/reconnect) signaling track reset.
    - Rule 8: Pure live-stream ingestion without downloading whole files.
    - Rule 10: Explicit camera state machine (OFFLINE, CONNECTING, ONLINE, DEGRADED, RECONNECTING, STOPPED).
    - Rule 11 & 12: Produces standardized FramePacket instances for the AI pipeline.
    - Rule 13: Strict isolation and camera-prefixed logging.
    """

    def __init__(
        self,
        camera_id: str,
        source: str,
        source_type: str = "rtsp",  # "rtsp", "hls", "file"
        fallback_source: Optional[str] = None,
        auto_reconnect: bool = True,
        stream_timeout_sec: float = 6.0,
        consecutive_failure_threshold: int = 15,
    ):
        self.camera_id = camera_id
        self.primary_source = source
        self.source = source
        self.source_type = source_type.lower()
        self.fallback_source = fallback_source
        self.auto_reconnect = auto_reconnect
        self.stream_timeout_sec = stream_timeout_sec
        self.consecutive_failure_threshold = consecutive_failure_threshold

        self.cap: Optional[cv2.VideoCapture] = None
        self.state: CameraState = CameraState.OFFLINE
        self.last_seen: Optional[datetime] = None
        self.frame_count: int = 0
        self.sequence_number: int = 0
        
        # Timing and PTS Tracking (Rules 2 & 3)
        self.last_pts_ms: float = 0.0
        self.nominal_fps: float = 25.0  # Diagnostic estimate only; never used for physics timing
        self._stream_start_mono: float = 0.0
        self._pts_offset_ms: float = 0.0
        
        # Discontinuity Detection (Rule 7)
        self._just_reconnected: bool = True
        self.last_error: Optional[str] = None
        
        # Failure & Degraded State Tracking (Rules 4 & 6)
        self._consecutive_read_failures: int = 0
        self._last_successful_read_mono: float = 0.0
        
        self._lock = threading.Lock()
        self._is_running: bool = False
        self._reconnect_handler = StreamReconnectHandler(
            camera_id=self.camera_id,
            reconnect_callback=self._do_connect,
            initial_delay=2.0,
            max_delay=30.0,
            backoff_factor=2.0,
        )

        # Synthetic generator variables for demo fallback
        self._synthetic_step: int = 0

    @property
    def status(self) -> str:
        """String representation of current lifecycle state."""
        return self.state.value

    def connect(self) -> bool:
        """Establish connection to the video stream (thread-safe)."""
        with self._lock:
            return self._do_connect()

    def _do_connect(self) -> bool:
        """Internal connection routine applying Rule 1 (RTSP over TCP) and HLS fallback."""
        self.state = CameraState.CONNECTING
        self.last_error = None
        logger.info(f"[{self.camera_id}] Connecting to {self.source_type.upper()} source: {self.source}")

        # Clean up existing capture if any
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception as e:
                logger.warning(f"[{self.camera_id}] Error releasing prior capture: {e}")
            self.cap = None

        try:
            # Rule 1: Enforce TCP for RTSP streams
            if self.source_type == "rtsp":
                transport = getattr(settings, "RTSP_TRANSPORT", "tcp")
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{transport}"
                self.cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
            elif self.source_type == "hls":
                self.cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
            else:  # local file / test clip
                self.cap = cv2.VideoCapture(self.source)

            # Validate connection by testing isOpened and reading initial frame
            if self.cap is not None and self.cap.isOpened():
                ok, test_frame = self.cap.read()
                if ok and test_frame is not None and test_frame.size > 0:
                    self.state = CameraState.ONLINE
                    self.last_seen = utc_now()
                    self._last_successful_read_mono = time.monotonic()
                    self._stream_start_mono = time.monotonic()
                    self._consecutive_read_failures = 0
                    self._just_reconnected = True  # Signal discontinuity for first post-connect frame

                    # Record nominal FPS for diagnostics (DO NOT USE for physics/speed calculations)
                    stream_fps = self.cap.get(cv2.CAP_PROP_FPS)
                    self.nominal_fps = stream_fps if (stream_fps and stream_fps > 0) else 25.0
                    self._is_running = True
                    logger.info(
                        f"[{self.camera_id}] Connected successfully to {self.source_type.upper()} "
                        f"(nominal container FPS: {self.nominal_fps:.1f}, TCP enforced)."
                    )
                    self._reconnect_handler.reset()
                    return True
                else:
                    logger.warning(f"[{self.camera_id}] Stream opened but failed to read initial frame.")

            # If RTSP failed and a fallback source (e.g. HLS) is available, attempt fallback (Rule 1)
            if self.source_type == "rtsp" and self.fallback_source and self.source != self.fallback_source:
                logger.warning(
                    f"[{self.camera_id}] RTSP stream unreachable. Attempting HLS fallback: {self.fallback_source}"
                )
                self.source = self.fallback_source
                self.source_type = "hls"
                if self.cap is not None:
                    try:
                        self.cap.release()
                    except Exception:
                        pass
                self.cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
                if self.cap is not None and self.cap.isOpened():
                    ok, test_frame = self.cap.read()
                    if ok and test_frame is not None and test_frame.size > 0:
                        self.state = CameraState.ONLINE
                        self.last_seen = utc_now()
                        self._last_successful_read_mono = time.monotonic()
                        self._stream_start_mono = time.monotonic()
                        self._consecutive_read_failures = 0
                        self._just_reconnected = True
                        self._is_running = True
                        logger.info(f"[{self.camera_id}] Successfully connected to HLS fallback stream.")
                        self._reconnect_handler.reset()
                        return True

            # Demo fallback if enabled
            if settings.DEMO_MODE:
                logger.warning(
                    f"[{self.camera_id}] Live stream unreachable. Activating DEMO synthetic feed (DEMO_MODE=True)."
                )
                self.state = CameraState.ONLINE
                self.last_seen = utc_now()
                self._last_successful_read_mono = time.monotonic()
                self._stream_start_mono = time.monotonic()
                self.nominal_fps = 25.0
                self._is_running = True
                self._just_reconnected = True
                self._reconnect_handler.reset()
                return True

            self.state = CameraState.OFFLINE
            self.last_error = f"Failed to connect to {self.source_type.upper()} stream at {self.source}"
            logger.error(f"[{self.camera_id}] Connection failed: {self.last_error}")
            return False

        except Exception as e:
            self.state = CameraState.OFFLINE
            self.last_error = str(e)
            logger.error(f"[{self.camera_id}] Exception during connect: {e}")

            if settings.DEMO_MODE:
                self.state = CameraState.ONLINE
                self.last_seen = utc_now()
                self._last_successful_read_mono = time.monotonic()
                self._stream_start_mono = time.monotonic()
                self.nominal_fps = 25.0
                self._is_running = True
                self._just_reconnected = True
                self._reconnect_handler.reset()
                return True

            return False

    def read_packet(self) -> Optional[FramePacket]:
        """
        Read a single video frame and wrap it in a FramePacket with container PTS and discontinuity flags.
        Conforms to Mandatory Rules 2, 3, 4, 6, 7, 11, 12.
        
        Returns:
            FramePacket if frame read was successful, or None if no frame is currently available.
        """
        with self._lock:
            if not self._is_running:
                return None

            now_mono = time.monotonic()

            # Real Capture Attempt
            if self.cap is not None and self.cap.isOpened():
                try:
                    ok, frame = self.cap.read()
                    if ok and frame is not None and frame.size > 0:
                        # Successful read
                        self._consecutive_read_failures = 0
                        self._last_successful_read_mono = now_mono
                        self.state = CameraState.ONLINE
                        self.last_seen = utc_now()
                        self.frame_count += 1
                        self.sequence_number += 1

                        # Rule 3: Extract Presentation Timestamp (PTS) from video stream
                        pts_ms = self._extract_pts_ms(now_mono)
                        
                        # Rule 7: Detect scene discontinuities
                        is_discontinuity = self._detect_discontinuity(pts_ms)
                        self.last_pts_ms = pts_ms

                        return FramePacket(
                            frame=frame,
                            pts_ms=pts_ms,
                            camera_id=self.camera_id,
                            sequence_number=self.sequence_number,
                            received_at=datetime.now(timezone.utc),
                            is_discontinuity=is_discontinuity,
                            source_type=self.source_type,
                        )
                    else:
                        # For local files, loop back to start if at end
                        if self.source_type == "file":
                            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            ok_loop, frame_loop = self.cap.read()
                            if ok_loop and frame_loop is not None and frame_loop.size > 0:
                                self.frame_count += 1
                                self.sequence_number += 1
                                self.last_seen = utc_now()
                                pts_ms = self._extract_pts_ms(now_mono)
                                # File rewind is a hard discontinuity (Rule 7)
                                self.last_pts_ms = pts_ms
                                return FramePacket(
                                    frame=frame_loop,
                                    pts_ms=pts_ms,
                                    camera_id=self.camera_id,
                                    sequence_number=self.sequence_number,
                                    received_at=datetime.now(timezone.utc),
                                    is_discontinuity=True,
                                    source_type=self.source_type,
                                )

                        # Rule 6: Tolerate transient decode warnings / read slips
                        self._handle_read_failure(now_mono)

                except Exception as e:
                    logger.warning(f"[{self.camera_id}] Exception during cap.read(): {e}")
                    self._handle_read_failure(now_mono)

            # If real capture is not active or closed, check reconnection or demo mode
            if self.cap is None or not self.cap.isOpened():
                if self.auto_reconnect and not settings.DEMO_MODE:
                    if self.state in (CameraState.RECONNECTING, CameraState.OFFLINE):
                        if self._reconnect_handler.should_attempt():
                            logger.warning(f"[{self.camera_id}] Triggering automatic reconnection...")
                            reconnected = self._reconnect_handler.attempt_reconnect_sync()
                            if reconnected and self.cap is not None and self.cap.isOpened():
                                ok, frame = self.cap.read()
                                if ok and frame is not None and frame.size > 0:
                                    self._consecutive_read_failures = 0
                                    self._last_successful_read_mono = time.monotonic()
                                    self.state = CameraState.ONLINE
                                    self.last_seen = utc_now()
                                    self.frame_count += 1
                                    self.sequence_number += 1
                                    pts_ms = self._extract_pts_ms(time.monotonic())
                                    self.last_pts_ms = pts_ms
                                    return FramePacket(
                                        frame=frame,
                                        pts_ms=pts_ms,
                                        camera_id=self.camera_id,
                                        sequence_number=self.sequence_number,
                                        received_at=datetime.now(timezone.utc),
                                        is_discontinuity=True,  # Reconnect causes discontinuity
                                        source_type=self.source_type,
                                    )
                    return None

                # Demo fallback frame generation if DEMO_MODE is True and no active capture
                if settings.DEMO_MODE:
                    frame = self._generate_synthetic_cctv_frame()
                    self.frame_count += 1
                    self.sequence_number += 1
                    self.last_seen = utc_now()
                    self.state = CameraState.ONLINE
                    pts_ms = float((time.time() - self._stream_start_mono) * 1000.0) if self._stream_start_mono > 0 else float(time.time() * 1000)
                    is_discontinuity = self._detect_discontinuity(pts_ms)
                    self.last_pts_ms = pts_ms
                    return FramePacket(
                        frame=frame,
                        pts_ms=pts_ms,
                        camera_id=self.camera_id,
                        sequence_number=self.sequence_number,
                        received_at=datetime.now(timezone.utc),
                        is_discontinuity=is_discontinuity,
                        source_type="demo",
                    )

            return None

    def _extract_pts_ms(self, current_mono: float) -> float:
        """
        Extract presentation timestamp (PTS) from video stream.
        Conforms to Rule 3 (frame timing driven by PTS).
        
        Documented Limitation:
        Certain live RTSP muxers / HLS chunks may not expose CAP_PROP_POS_MSEC via OpenCV.
        When CAP_PROP_POS_MSEC returns <= 0, we compute the relative monotonic stream elapsed
        time in milliseconds to maintain strict monotonic temporal progression.
        """
        pos_msec = self.cap.get(cv2.CAP_PROP_POS_MSEC) if self.cap is not None else 0.0
        if pos_msec and pos_msec > 0.0:
            return float(pos_msec)
        
        # High-resolution monotonic stream clock fallback
        elapsed_ms = (current_mono - self._stream_start_mono) * 1000.0
        return float(self._pts_offset_ms + elapsed_ms)

    def _detect_discontinuity(self, current_pts_ms: float) -> bool:
        """
        Detect scene / stream discontinuities conforming to Rule 7.
        Triggers if:
        1. First frame after connection / reconnection
        2. PTS moved backward by > 500ms (stream loop / PTS reset)
        3. PTS jumped forward by > 5000ms (stream gap / drop)
        """
        if self._just_reconnected:
            self._just_reconnected = False
            logger.info(f"[{self.camera_id}] Discontinuity signaled: Initial frame after connection/reconnect.")
            return True

        if self.last_pts_ms > 0:
            # Time rollback (e.g. stream loop)
            if current_pts_ms < (self.last_pts_ms - 500.0):
                logger.warning(
                    f"[{self.camera_id}] Discontinuity detected: PTS rolled back "
                    f"from {self.last_pts_ms:.1f}ms to {current_pts_ms:.1f}ms."
                )
                return True
            # Large jump forward (> 5.0 seconds)
            if (current_pts_ms - self.last_pts_ms) > 5000.0:
                logger.warning(
                    f"[{self.camera_id}] Discontinuity detected: Large PTS jump "
                    f"({current_pts_ms - self.last_pts_ms:.1f}ms gap)."
                )
                return True

        return False

    def _handle_read_failure(self, current_mono: float):
        """
        Handle intermittent frame read failure conforming to Rules 4 & 6.
        Tolerates transient drops (DEGRADED) before declaring RECONNECTING.
        """
        self._consecutive_read_failures += 1
        time_since_last_read = current_mono - self._last_successful_read_mono

        if self._consecutive_read_failures >= 3 and self._consecutive_read_failures < self.consecutive_failure_threshold:
            if self.state != CameraState.DEGRADED:
                self.state = CameraState.DEGRADED
                logger.warning(
                    f"[{self.camera_id}] Stream degraded: {self._consecutive_read_failures} consecutive empty reads "
                    f"({time_since_last_read:.1f}s since last frame)."
                )

        if (
            self._consecutive_read_failures >= self.consecutive_failure_threshold
            or time_since_last_read > self.stream_timeout_sec
        ):
            if self.state != CameraState.RECONNECTING:
                self.state = CameraState.RECONNECTING
                self.last_error = f"Sustained frame read failure ({self._consecutive_read_failures} fails, {time_since_last_read:.1f}s timeout)"
                logger.error(f"[{self.camera_id}] {self.last_error}. Marking RECONNECTING.")

    def _generate_synthetic_cctv_frame(self) -> np.ndarray:
        """Generate high-quality synthetic CCTV traffic scene for demo mode."""
        self._synthetic_step += 1
        h, w = 480, 640
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:] = (35, 40, 45)

        # Draw road lanes
        cv2.rectangle(frame, (100, 0), (540, h), (55, 60, 65), -1)
        dash_offset = (self._synthetic_step * 8) % 60
        for y in range(-60 + dash_offset, h + 60, 60):
            cv2.line(frame, (320, max(0, y)), (320, min(h, y + 30)), (230, 230, 230), 3)

        cv2.line(frame, (100, 0), (100, h), (255, 255, 255), 4)
        cv2.line(frame, (540, 0), (540, h), (255, 255, 255), 4)

        # Simulated moving vehicles
        car1_y = ((self._synthetic_step * 5) % (h + 200)) - 100
        if -80 < car1_y < h + 80:
            cv2.rectangle(frame, (170, int(car1_y)), (270, int(car1_y + 130)), (180, 50, 40), -1)
            cv2.rectangle(frame, (170, int(car1_y)), (270, int(car1_y + 130)), (230, 230, 230), 2)
            cv2.rectangle(frame, (180, int(car1_y + 20)), (260, int(car1_y + 50)), (30, 30, 30), -1)
            cv2.rectangle(frame, (195, int(car1_y + 115)), (245, int(car1_y + 128)), (255, 255, 255), -1)
            cv2.putText(frame, "GJ01AB1234", (197, int(car1_y + 125)), cv2.FONT_HERSHEY_SIMPLEX, 0.25, (0, 0, 0), 1)

        car2_y = h - (((self._synthetic_step * 4) % (h + 250)) - 100)
        if -80 < car2_y < h + 80:
            cv2.rectangle(frame, (370, int(car2_y)), (470, int(car2_y + 140)), (40, 120, 200), -1)
            cv2.rectangle(frame, (370, int(car2_y)), (470, int(car2_y + 140)), (230, 230, 230), 2)
            cv2.rectangle(frame, (380, int(car2_y + 80)), (460, int(car2_y + 110)), (30, 30, 30), -1)
            cv2.rectangle(frame, (395, int(car2_y + 10)), (445, int(car2_y + 23)), (255, 255, 255), -1)
            cv2.putText(frame, "MH02CD5678", (397, int(car2_y + 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.25, (0, 0, 0), 1)

        # HUD Overlay
        curr_time = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"TRINETRA AI CCTV [{self.camera_id}] ({self.state.value})", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 180), 2)
        cv2.putText(frame, f"TIME: {curr_time}", (15, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.putText(frame, f"FRAMES: {self.frame_count} | SEQ: {self.sequence_number}", (15, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
        return frame

    def is_alive(self) -> bool:
        """Check if camera stream is active and operational."""
        return self._is_running and self.state in (CameraState.ONLINE, CameraState.DEGRADED)

    def release(self):
        """Safely release OpenCV VideoCapture resources (Rule 9 & 10)."""
        with self._lock:
            self._is_running = False
            self.state = CameraState.STOPPED
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception as e:
                    logger.warning(f"[{self.camera_id}] Error during cap.release(): {e}")
                self.cap = None
            logger.info(f"[{self.camera_id}] Stream released and stopped.")
