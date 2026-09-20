import os
import sys
from pathlib import Path
import threading
import time
from typing import Dict, List, Optional, Callable
from uuid import uuid4
from dataclasses import dataclass, replace

# Allow running this file directly as a script
if __name__ == "__main__" and not __package__:
    project_root = Path(__file__).resolve().parents[3]
    backend_root = Path(__file__).resolve().parents[2]
    for p in [str(project_root), str(backend_root)]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    __package__ = "backend.app.camera"

# Resolved through app/core/vision so the API also boots on hosts without the
# CV extras (serverless/API-only mode) — see that module for the contract.
from ..core.vision import cv2, np

from ..core.config import settings
from ..core.logging_config import logger
from .stream import CameraStream
from .packet import FramePacket


@dataclass
class LiveViewControl:
    enabled: bool
    touched_at: float
    readers: int = 0
    sequence: int = 0


class CameraManager:
    """
    Multi-camera manager for CCTV ingestion and frame distribution.
    Conforms to Mandatory Rules 1 - 14:
    - Rule 9: Resource pacing (creates/releases resources on-demand).
    - Rule 10: Explicit 6-state lifecycle tracking.
    - Rule 11 & 12: FramePacket pipeline dispatch with exact PTS.
    - Rule 13: Strict camera isolation (failures never propagate).
    - Rule 14: Subsampled frame selection with preserved timestamps.
    """

    def __init__(self):
        self._streams: Dict[str, CameraStream] = {}
        self._latest_packets: Dict[str, FramePacket] = {}
        self._latest_annotated_frames: Dict[str, np.ndarray] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        # camera_id (lowercase) -> monotonic time of the last REAL frame that
        # the live view delivered (worker or on-demand decode). Placeholder
        # "NO SIGNAL" frames never update this, so the UI can tell a live
        # picture from a no-signal placeholder.
        self._live_signal: Dict[str, float] = {}
        self._lock = threading.RLock()
        self._pipeline_callback: Optional[Callable[[FramePacket], None]] = None
        self._view_controls: dict[tuple[str, str], LiveViewControl] = {}

    def _note_live_signal(self, camera_id: str) -> None:
        key = (camera_id or "").lower()
        if key:
            self._live_signal[key] = time.monotonic()

    def has_live_signal(self, camera_id: str, window_sec: float = 6.0) -> bool:
        """True when this camera's live view received a real frame within the
        last `window_sec` seconds (False for placeholder/NO-SIGNAL streams)."""
        last = self._live_signal.get((camera_id or "").lower())
        return bool(last is not None and (time.monotonic() - last) <= window_sec)

    def set_pipeline_callback(self, callback: Optional[Callable[[FramePacket], None]]):
        """Set callback to receive FramePacket objects for AI processing."""
        with self._lock:
            self._pipeline_callback = callback

    def add_camera(
        self,
        camera_id: str,
        source: str,
        source_type: str = "rtsp",
        fallback_source: Optional[str] = None,
        auto_start: bool = True,
    ) -> CameraStream:
        """
        Register a new CCTV camera stream.
        Applies Rule 1 (TCP RTSP + HLS Fallback) and Rule 9 (Paced Resources).
        """
        with self._lock:
            if camera_id in self._streams:
                logger.info(f"[{camera_id}] Camera already exists in manager. Updating stream.")
                self.stop_camera(camera_id)

            stream = CameraStream(
                camera_id=camera_id,
                source=source,
                source_type=source_type,
                fallback_source=fallback_source,
            )
            self._streams[camera_id] = stream

        if auto_start:
            self.start_camera(camera_id)

        return stream

    def remove_camera(self, camera_id: str) -> bool:
        """Stop and remove a camera from management, releasing all resources (Rule 9)."""
        self.stop_camera(camera_id)
        with self._lock:
            if camera_id in self._streams:
                del self._streams[camera_id]
            if camera_id in self._latest_packets:
                del self._latest_packets[camera_id]
            if camera_id in self._latest_annotated_frames:
                del self._latest_annotated_frames[camera_id]
            self._live_signal.pop(camera_id.lower(), None)
            logger.info(f"[{camera_id}] Camera removed from CameraManager.")
            return True
        return False

    def start_camera(self, camera_id: str) -> bool:
        """Start frame acquisition worker thread for a camera."""
        with self._lock:
            if camera_id not in self._streams:
                logger.error(f"[{camera_id}] Cannot start camera: not found in manager.")
                return False

            stream = self._streams[camera_id]

            # Check if already running
            if camera_id in self._threads and self._threads[camera_id].is_alive():
                logger.warning(f"[{camera_id}] Worker thread already running.")
                return True

            stop_event = threading.Event()
            self._stop_events[camera_id] = stop_event

            # Connect stream
            stream.connect()

            # Start worker thread
            worker = threading.Thread(
                target=self._camera_worker,
                args=(camera_id, stream, stop_event),
                daemon=True,
                name=f"CameraWorker-{camera_id}",
            )
            self._threads[camera_id] = worker
            worker.start()
            logger.info(f"[{camera_id}] Worker thread started.")
            return True

    def stop_camera(self, camera_id: str) -> bool:
        """Stop frame acquisition and release resources (Rule 9 & 10)."""
        with self._lock:
            if camera_id not in self._streams:
                return False

            if camera_id in self._stop_events:
                self._stop_events[camera_id].set()

            stream = self._streams[camera_id]
            stream.release()

        # Wait for thread termination outside lock
        if camera_id in self._threads:
            thread = self._threads[camera_id]
            if thread.is_alive():
                thread.join(timeout=2.0)
            with self._lock:
                if camera_id in self._threads:
                    del self._threads[camera_id]
                if camera_id in self._stop_events:
                    del self._stop_events[camera_id]

        with self._lock:
            self._latest_packets.pop(camera_id, None)
            self._latest_annotated_frames.pop(camera_id, None)
            self._live_signal.pop(camera_id.lower(), None)
        from ..services.live_anpr_service import live_anpr_service
        live_anpr_service.forget(camera_id)
        logger.info(f"[{camera_id}] Stopped and resources released.")
        return True

    def restart_camera(self, camera_id: str) -> bool:
        """Restart a camera stream safely."""
        logger.info(f"[{camera_id}] Restarting camera...")
        self.stop_camera(camera_id)
        time.sleep(0.5)
        return self.start_camera(camera_id)

    def get_camera(self, camera_id: str) -> Optional[CameraStream]:
        """Get stream instance by camera_id."""
        with self._lock:
            return self._streams.get(camera_id)

    def list_cameras(self) -> List[Dict]:
        """List all cameras with full lifecycle state reporting (Rule 10)."""
        with self._lock:
            results = []
            for cam_id, stream in self._streams.items():
                results.append({
                    "camera_id": cam_id,
                    "source": stream.source,
                    "source_type": stream.source_type,
                    "status": stream.state.value,
                    "is_alive": stream.is_alive(),
                    "fps": stream.nominal_fps,
                    "frame_count": stream.frame_count,
                    "sequence_number": stream.sequence_number,
                    "last_pts_ms": stream.last_pts_ms,
                    "last_seen": stream.last_seen,
                    "last_error": stream.last_error,
                })
            return results

    def get_camera_status(self, camera_id: str) -> Optional[Dict]:
        """Get status dictionary for a specific camera."""
        stream = self.get_camera(camera_id)
        if not stream:
            return None
        return {
            "camera_id": stream.camera_id,
            "source_type": stream.source_type,
            "status": stream.state.value,
            "is_alive": stream.is_alive(),
            "fps": stream.nominal_fps,
            "frame_count": stream.frame_count,
            "sequence_number": stream.sequence_number,
            "last_pts_ms": stream.last_pts_ms,
            "last_seen": stream.last_seen,
            "last_error": stream.last_error,
        }

    def update_annotated_frame(self, camera_id: str, frame: np.ndarray):
        """Update the latest annotated frame with AI overlays for display."""
        with self._lock:
            self._latest_annotated_frames[camera_id] = frame

    def get_latest_frame(self, camera_id: str, annotated: bool = True) -> Optional[np.ndarray]:
        """Get latest frame for a camera (annotated or raw)."""
        with self._lock:
            if annotated and camera_id in self._latest_annotated_frames:
                return self._latest_annotated_frames[camera_id].copy()
            if camera_id in self._latest_packets:
                return self._latest_packets[camera_id].frame.copy()
            return None

    def get_latest_packet(self, camera_id: str) -> Optional[FramePacket]:
        """Get the latest ingested FramePacket for a camera."""
        with self._lock:
            return self._latest_packets.get(camera_id)

    # Stream types openable on demand for a live view. Files are local
    # recordings (stamped as demo footage); rtsp/hls are real network cams.
    _ONDEMAND_TYPES = {"file", "rtsp", "hls"}

    def _ondemand_source(self, camera_id: str):
        """Return (source, is_file) if this camera can be opened on demand."""
        with self._lock:
            stream = self._streams.get(camera_id) or self._streams.get(camera_id.upper())
            if stream is None:
                return None
            stype = (getattr(stream, "source_type", "") or "").lower()
            if stype not in self._ONDEMAND_TYPES:
                return None
            source = (stream.source or "").strip()
        if not source:
            return None
        if stype == "file":
            return (source, True) if os.path.exists(source) else None
        return (source, False)  # real network camera URL

    @staticmethod
    def _stamp_source_osd(frame, is_file: bool):
        """Burn an honest source label into on-demand live-view frames.

        Recorded clips are explicitly marked NOT LIVE so demo footage can
        never be mistaken for a real camera; real network streams are
        marked LIVE.
        """
        label = "RECORDED FOOTAGE - NOT LIVE" if is_file else "LIVE SOURCE"
        h, w = frame.shape[:2]
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        x2, y2 = w - 10, h - 12
        cv2.rectangle(frame, (x2 - tw - 10, y2 - th - 8), (x2 + 2, y2 + 4), (15, 18, 24), -1)
        color = (0, 200, 255) if is_file else (0, 255, 0)
        cv2.putText(frame, label, (x2 - tw - 5, y2), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, color, 1, cv2.LINE_AA)
        return frame

    def _ondemand_candidates(self, camera_id: str):
        """Ordered (source, is_file) candidates for an on-demand live view.

        Sentinel cameras: authenticated RTSP first (TCP), then authenticated
        HLS over HTTPS (works where port 8554 is blocked), then the registry
        URL as-is. Credentials are built here, backend-side, never stored.
        """
        resolved = self._ondemand_source(camera_id)
        if resolved is None:
            return []
        source, is_file = resolved
        if is_file:
            return [(source, True)]
        candidates = []
        try:
            from ..services import sentinel_stream_service as svc

            with self._lock:
                stream = self._streams.get(camera_id) or self._streams.get(camera_id.upper())
            registry_url = (getattr(stream, "primary_source", "") or source)
            if svc.is_sentinel_camera(registry_url) or svc.is_sentinel_camera(source):
                cid = svc.validate_camera_id(camera_id)
                if svc.credentials_configured():
                    candidates.append((svc.get_rtsp_url(cid), False))
                    candidates.append((svc.get_authenticated_hls_url(cid), False))
                candidates.append((svc.get_hls_url(cid), False))
        except Exception as exc:
            logger.warning(f"[{camera_id.upper()}] Could not build Sentinel sources: {exc}")
        if not any(c[0] == source for c in candidates):
            candidates.append((source, False))
        return candidates

    @staticmethod
    def _open_ondemand_capture(source: str) -> "cv2.VideoCapture":
        """Open a source for on-demand decoding (RTSP forced over TCP)."""
        if source.lower().startswith("rtsp://"):
            transport = getattr(settings, "RTSP_TRANSPORT", "tcp")
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{transport}"
            return cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        if source.lower().startswith(("http://", "https://")):
            return cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        return cv2.VideoCapture(source)

    @classmethod
    def _read_ondemand_frame(cls, cap: "cv2.VideoCapture", source: str):
        """Read one frame for an on-demand live view, looping the file safely."""
        ok, frame = cap.read() if cap.isOpened() else (False, None)
        if not (ok and frame is not None and frame.size > 0):
            # Some containers cannot seek backwards reliably — reopen instead.
            try:
                cap.release()
            except Exception:
                pass
            if "://" in source:
                time.sleep(0.4)  # do not hammer an unreachable network source
                # Force the FFmpeg backend for network URLs (default backend
                # probing spams CAP_IMAGES errors and can fail on Windows).
                cap.open(source, cv2.CAP_FFMPEG)
            else:
                cap.open(source)
            ok, frame = cap.read()
        if not (ok and frame is not None and frame.size > 0):
            return None
        h, w = frame.shape[:2]
        if w > 1280:  # keep on-demand views cheap to decode and stream
            scale = 1280.0 / w
            frame = cv2.resize(frame, (1280, int(round(h * scale))), interpolation=cv2.INTER_AREA)
        return frame

    def _view_control(self, camera_id: str, viewer_id: str, initial: bool) -> LiveViewControl:
        # Caller holds the manager lock. Bound abandoned control requests;
        # live readers release their entry when their HTTP stream closes.
        now = time.monotonic()
        for key, control in list(self._view_controls.items()):
            if not control.readers and now-control.touched_at > 15:
                self._view_controls.pop(key, None)
        key = (camera_id.strip().upper(), viewer_id)
        control = self._view_controls.get(key)
        if control is None:
            if len(self._view_controls) >= 128:
                raise ValueError("Live viewer capacity reached")
            control = self._view_controls[key] = LiveViewControl(initial, now)
        control.touched_at = now
        return control

    def set_view_detection(self, camera_id: str, viewer_id: str, enabled: bool, sequence: int = 0) -> bool:
        with self._lock:
            control = self._view_control(camera_id, viewer_id, enabled)
            if sequence >= control.sequence:
                control.enabled, control.sequence = enabled, sequence
            return control.enabled

    def generate_mjpeg_stream(self, camera_id: str, detect_vehicles: bool = False,
                              viewer_id: Optional[str] = None, initial_detection: bool = True):
        """Yield multipart MJPEG stream frames for HTTP live view.

        When no resident worker is running for the camera (e.g. file-backed
        demo cameras with AUTO_START_CAMERAS off), the source file is decoded
        on demand for the lifetime of this HTTP connection only.

        With ``detect_vehicles=True`` frames are submitted without waiting for
        inference. Only fresh cached ANPR boxes/numbers are drawn on playback.
        """
        ondemand_cap = None
        ondemand_source = None
        ondemand_is_file = True
        ondemand_candidates = None
        ondemand_failures = 0
        detector = None
        control = None
        if viewer_id:
            with self._lock:
                control = self._view_control(camera_id, viewer_id, initial_detection)
                control.readers += 1
        source_id = f"mjpeg:{uuid4().hex}"
        if detect_vehicles:
            from ..services.live_anpr_service import live_anpr_service
            detector = live_anpr_service
        try:
            while True:
                started = time.monotonic()
                frame = self.get_latest_frame(camera_id, annotated=False)
                if frame is None:
                    frame = self.get_latest_frame(camera_id.upper(), annotated=False)
                # A cached frame is not a live signal. The worker updates this
                # timestamp only when it actually receives a new source frame.
                if frame is not None and not self.has_live_signal(camera_id):
                    frame = None
                resident = frame is not None
                if frame is None and ondemand_source is None and ondemand_cap is None:
                    if ondemand_candidates is None:
                        ondemand_candidates = self._ondemand_candidates(camera_id)
                    if ondemand_candidates:
                        ondemand_source, ondemand_is_file = ondemand_candidates.pop(0)
                        ondemand_cap = self._open_ondemand_capture(ondemand_source)
                        ondemand_failures = 0
                        from ..services.sentinel_stream_service import redact as _redact
                        kind = "local recording" if ondemand_is_file else "real network stream"
                        logger.info(
                            f"[{camera_id.upper()}] On-demand live view decoding {kind}: {_redact(ondemand_source)}"
                        )
                if frame is None and ondemand_cap is not None:
                    frame = self._read_ondemand_frame(ondemand_cap, ondemand_source)
                    if frame is not None:
                        ondemand_failures = 0
                        self._note_live_signal(camera_id)  # real frame from on-demand decode
                    elif not ondemand_is_file:
                        # Network source not delivering: after a few misses, move
                        # on to the next candidate (e.g. RTSP blocked -> HLS).
                        ondemand_failures += 1
                        if ondemand_failures >= 25 and ondemand_candidates:
                            from ..services.sentinel_stream_service import redact as _redact
                            logger.warning(
                                f"[{camera_id.upper()}] No frames from {_redact(ondemand_source)} — trying next source"
                            )
                            try:
                                ondemand_cap.release()
                            except Exception:
                                pass
                            ondemand_cap = None
                            ondemand_source = None
                if frame is not None:
                    if detector is not None and (control is None or control.enabled):
                        media_time = None
                        if not resident:
                            pts = float(ondemand_cap.get(cv2.CAP_PROP_POS_MSEC) or 0) / 1000.0
                            media_time = pts if ondemand_is_file else None
                            detector.submit(camera_id, frame, source_id=source_id, media_time=media_time)
                        else:
                            packet = self.get_latest_packet(camera_id) or self.get_latest_packet(camera_id.upper())
                            if packet is not None:
                                media_time = packet.pts_ms / 1000.0
                        frame = detector.annotate(camera_id, frame,
                                                  source_id="resident" if resident else source_id,
                                                  media_time=media_time)
                    if not resident:
                        frame = self._stamp_source_osd(frame, ondemand_is_file)
                if frame is None:
                    placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                    placeholder[:] = (20, 24, 30)
                    cv2.putText(
                        placeholder,
                        f"NO SIGNAL - {camera_id}",
                        (180, 240),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (100, 100, 255),
                        2,
                    )
                    frame = placeholder

                ret, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if not ret:
                    time.sleep(0.04)
                    continue

                frame_bytes = buffer.tobytes()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )
                # Preserve file playback speed instead of decoding a 25 fps
                # recording at half speed. AI sampling has its own clock.
                fps = float(ondemand_cap.get(cv2.CAP_PROP_FPS) or 25) if ondemand_cap else 25.0
                time.sleep(max(0.001, 1.0 / max(1.0, fps) - (time.monotonic() - started)))
        finally:
            if control is not None:
                with self._lock:
                    control.readers -= 1
                    if control.readers <= 0:
                        self._view_controls.pop((camera_id.strip().upper(), viewer_id), None)
            if ondemand_cap is not None:
                try:
                    ondemand_cap.release()
                except Exception:
                    pass
            # Do not forget shared ANPR state when just one viewer disconnects.
            # Idle eviction / camera stop releases it, preserving duplicate suppression.

    def _camera_worker(self, camera_id: str, stream: CameraStream, stop_event: threading.Event):
        """
        Background worker reading frames, creating FramePackets, and dispatching to AI pipeline.
        Conforms to Rule 13 (camera isolation) and Rule 14 (subsampled frame dispatching).
        """
        logger.info(f"[{camera_id}] Ingestion worker active.")
        process_every_n = max(1, getattr(settings, "PROCESS_EVERY_N_FRAMES", 1))
        pending_discontinuity = False

        while not stop_event.is_set():
            try:
                start_time = time.monotonic()
                packet = stream.read_packet()

                if packet is not None:
                    with self._lock:
                        self._latest_packets[camera_id] = packet

                        # get_latest_frame already falls back to this raw packet.
                        # Caching the FIRST raw frame as "annotated" froze playback.
                        if packet.source_type != "demo":
                            self._note_live_signal(camera_id)
                    pending_discontinuity = pending_discontinuity or packet.is_discontinuity

                    # Rule 14: Subsample frames while strictly preserving packet PTS
                    if packet.sequence_number % process_every_n == 0:
                        callback = self._pipeline_callback
                        if callback is not None:
                            try:
                                # A reconnect/loop may fall on a skipped frame;
                                # carry its reset signal onto the next sample.
                                callback(replace(packet, is_discontinuity=pending_discontinuity))
                                pending_discontinuity = False
                            except Exception as cb_err:
                                logger.error(f"[{camera_id}] Error in AI pipeline callback: {cb_err}")

                else:
                    # No frame returned (transient slip or reconnecting)
                    time.sleep(0.05)

                # Pace loop according to nominal rate
                elapsed = time.monotonic() - start_time
                target_interval = 1.0 / max(stream.nominal_fps, 10.0)
                sleep_time = max(0.001, target_interval - elapsed)
                time.sleep(sleep_time)

            except Exception as e:
                # Rule 13: Top-level exception isolation
                logger.error(f"[{camera_id}] Unexpected error in camera worker: {e}")
                time.sleep(0.5)

        logger.info(f"[{camera_id}] Ingestion worker terminated.")

# Global singleton instance
camera_manager = CameraManager()
