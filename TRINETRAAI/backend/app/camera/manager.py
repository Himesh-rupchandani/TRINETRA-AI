import os
import sys
from pathlib import Path
import threading
import time
import uuid
from typing import Dict, List, Optional, Callable, Tuple
import cv2
import numpy as np

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
from .stream import CameraStream
from .packet import FramePacket, CameraState


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
        self._lock = threading.RLock()
        self._pipeline_callback: Optional[Callable[[FramePacket], None]] = None

    def set_pipeline_callback(self, callback: Callable[[FramePacket], None]):
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
        # Never hold the manager lock while stopping/joining a decoder worker:
        # that worker briefly takes the same lock to publish its latest packet.
        # Holding it here can turn a source change into a two-second UI stall.
        with self._lock:
            exists = camera_id in self._streams
        if exists:
            logger.info(f"[{camera_id}] Camera already exists in manager. Updating stream.")
            self.stop_camera(camera_id)

        stream = CameraStream(
            camera_id=camera_id,
            source=source,
            source_type=source_type,
            fallback_source=fallback_source,
        )
        with self._lock:
            # A changed source begins with a clean frame/tracker timeline; do
            # not briefly show a stale box/frame from the previous connection.
            self._latest_packets.pop(camera_id, None)
            self._latest_annotated_frames.pop(camera_id, None)
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
            logger.info(f"[{camera_id}] Camera removed from CameraManager.")
            return True
        return False

    def start_camera(self, camera_id: str) -> bool:
        """Start a non-blocking frame-acquisition worker for a camera.

        ``VideoCapture`` can take several seconds while an RTSP/HLS endpoint is
        unavailable.  Connection therefore happens inside the worker, not in
        the API/request thread that starts the camera.
        """
        with self._lock:
            if camera_id not in self._streams:
                logger.error(f"[{camera_id}] Cannot start camera: not found in manager.")
                return False
            stream = self._streams[camera_id]

            worker = self._threads.get(camera_id)
            if worker is not None and worker.is_alive():
                logger.warning(f"[{camera_id}] Worker thread already running.")
                return True

            stop_event = threading.Event()
            worker = threading.Thread(
                target=self._camera_worker,
                args=(camera_id, stream, stop_event),
                daemon=True,
                name=f"CameraWorker-{camera_id}",
            )
            self._stop_events[camera_id] = stop_event
            self._threads[camera_id] = worker

        worker.start()
        logger.info(f"[{camera_id}] Worker thread started.")
        return True

    def stop_camera(self, camera_id: str) -> bool:
        """Stop frame acquisition and release resources (Rule 9 & 10)."""
        with self._lock:
            stream = self._streams.get(camera_id)
            if stream is None:
                return False
            stop_event = self._stop_events.get(camera_id)
            worker = self._threads.get(camera_id)
            if stop_event is not None:
                # Also interrupts an exponential-backoff wait in read_packet().
                stop_event.set()

        # Release/join outside the manager lock. A worker may currently be
        # publishing a frame and must be allowed to complete that small section.
        stream.release()
        if worker is not None and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=2.0)

        with self._lock:
            # Do not accidentally discard a replacement worker that was
            # registered by a concurrent source update.
            if self._threads.get(camera_id) is worker:
                self._threads.pop(camera_id, None)
            if self._stop_events.get(camera_id) is stop_event:
                self._stop_events.pop(camera_id, None)

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
        """List camera lifecycle state without exposing private source URLs."""
        from ..services.sentinel_stream_service import redact, redact_text

        with self._lock:
            results = []
            for cam_id, stream in self._streams.items():
                results.append({
                    "camera_id": cam_id,
                    "source": redact(stream.source),
                    "source_type": stream.source_type,
                    "status": stream.state.value,
                    "is_alive": stream.is_alive(),
                    "fps": stream.nominal_fps,
                    "frame_count": stream.frame_count,
                    "sequence_number": stream.sequence_number,
                    "last_pts_ms": stream.last_pts_ms,
                    "last_seen": stream.last_seen,
                    "last_error": redact_text(stream.last_error),
                })
            return results

    def get_camera_status(self, camera_id: str) -> Optional[Dict]:
        """Get status diagnostics without returning a private source/secret."""
        from ..services.sentinel_stream_service import redact_text

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
            "last_error": redact_text(stream.last_error),
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
        label = "RECORDED DEMO FOOTAGE - NOT LIVE" if is_file else "LIVE SOURCE"
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
            from ..services.sentinel_stream_service import redact_text

            logger.warning("[%s] Could not build Sentinel sources: %s", camera_id.upper(), redact_text(exc))
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
    def _read_ondemand_frame(cls, cap: "cv2.VideoCapture", source: str) -> Tuple[Optional[np.ndarray], bool]:
        """Read one frame and report whether its source was reopened.

        The reopen flag is important to the vehicle tracker: a reconnect/file
        loop is a temporal discontinuity, not a continuation of the previous
        traffic scene.
        """
        reopened = False
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
            reopened = True
            ok, frame = cap.read()
        if not (ok and frame is not None and frame.size > 0):
            return None, reopened
        h, w = frame.shape[:2]
        if w > 1280:  # keep on-demand views cheap to decode and stream
            scale = 1280.0 / w
            frame = cv2.resize(frame, (1280, int(round(h * scale))), interpolation=cv2.INTER_AREA)
        return frame, reopened

    def generate_mjpeg_stream(self, camera_id: str, detect_vehicles: bool = False):
        """Yield a bounded, on-demand multipart MJPEG camera view.

        Detection sessions use raw frame packets plus their real PTS/sequence
        number.  A model run can be throttled for hardware capacity, but the
        tracker is advanced for every new live frame rather than repainting a
        frozen set of boxes.  No camera resource is retained after the HTTP
        client disconnects.
        """
        ondemand_cap = None
        ondemand_source = None
        ondemand_is_file = True
        ondemand_candidates = None
        ondemand_failures = 0
        ondemand_sequence = 0
        ondemand_clock_started = time.monotonic()
        detector = None
        detection_session_key = None
        last_annotation_frame_key = None
        if detect_vehicles:
            from ..services.vehicle_detection_service import vehicle_detection_service

            detector = vehicle_detection_service
            # Different browser clients need independent tracker state. The
            # model remains shared, so this costs no extra model memory.
            detection_session_key = f"{camera_id.lower()}:{uuid.uuid4().hex}"

        try:
            while True:
                frame = None
                pts_ms = None
                frame_key = None
                is_discontinuity = False

                # For the detection route always take the raw packet. An
                # external pipeline may already have drawn overlays into the
                # annotated cache; running detection over that would duplicate
                # boxes and pollute model input.
                if detect_vehicles:
                    packet = self.get_latest_packet(camera_id) or self.get_latest_packet(camera_id.upper())
                    if packet is not None:
                        frame = packet.frame.copy()
                        pts_ms = packet.pts_ms
                        # Object identity scopes the sequence to this capture
                        # generation; a replacement stream may restart at 1.
                        frame_key = ("resident", id(packet), packet.sequence_number)
                        is_discontinuity = bool(packet.is_discontinuity)
                else:
                    frame = self.get_latest_frame(camera_id, annotated=True)
                    if frame is None:
                        frame = self.get_latest_frame(camera_id.upper(), annotated=True)

                if frame is None and ondemand_source is None and ondemand_cap is None:
                    if ondemand_candidates is None:
                        ondemand_candidates = self._ondemand_candidates(camera_id)
                    if ondemand_candidates:
                        ondemand_source, ondemand_is_file = ondemand_candidates.pop(0)
                        ondemand_cap = self._open_ondemand_capture(ondemand_source)
                        ondemand_failures = 0
                        ondemand_clock_started = time.monotonic()
                        from ..services.sentinel_stream_service import redact as _redact

                        kind = "local recording" if ondemand_is_file else "real network stream"
                        logger.info(
                            "[%s] On-demand live view decoding %s: %s",
                            camera_id.upper(),
                            kind,
                            _redact(ondemand_source),
                        )

                if frame is None and ondemand_cap is not None:
                    frame, reopened = self._read_ondemand_frame(ondemand_cap, ondemand_source)
                    if frame is not None:
                        ondemand_failures = 0
                        ondemand_sequence += 1
                        frame_key = ("ondemand", ondemand_sequence)
                        is_discontinuity = reopened
                        try:
                            source_pts = float(ondemand_cap.get(cv2.CAP_PROP_POS_MSEC))
                        except Exception:
                            source_pts = 0.0
                        # CAP_PROP_POS_MSEC is authoritative when exposed.
                        # Otherwise use a connection-relative monotonic stream
                        # clock; never synthesize timing from nominal FPS.
                        pts_ms = source_pts if source_pts > 0.0 else (time.monotonic() - ondemand_clock_started) * 1000.0
                        frame = self._stamp_source_osd(frame, ondemand_is_file)
                    elif not ondemand_is_file:
                        # Network source not delivering: after a few misses, move
                        # on to the next candidate (e.g. RTSP blocked -> HLS).
                        ondemand_failures += 1
                        if ondemand_failures >= 25 and ondemand_candidates:
                            from ..services.sentinel_stream_service import redact as _redact

                            logger.warning(
                                "[%s] No frames from %s — trying next source",
                                camera_id.upper(),
                                _redact(ondemand_source),
                            )
                            try:
                                ondemand_cap.release()
                            except Exception:
                                pass
                            ondemand_cap = None
                            ondemand_source = None

                if frame is not None and detector is not None and detection_session_key is not None:
                    shared_frame_key = (
                        (camera_id.lower(), frame_key)
                        if isinstance(frame_key, tuple) and frame_key and frame_key[0] == "resident"
                        else None
                    )
                    # The same latest resident packet can be emitted more than
                    # once while the browser is waiting. Do not reset a tracker
                    # repeatedly because its packet carries a first-frame flag.
                    if frame_key == last_annotation_frame_key:
                        is_discontinuity = False
                    else:
                        last_annotation_frame_key = frame_key
                    frame = detector.annotate(
                        detection_session_key,
                        frame,
                        pts_ms=pts_ms,
                        frame_key=frame_key,
                        shared_frame_key=shared_frame_key,
                        is_discontinuity=is_discontinuity,
                    )

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
                time.sleep(0.08)  # ~12 FPS preview pacing; capture remains background work.
        finally:
            if ondemand_cap is not None:
                try:
                    ondemand_cap.release()
                except Exception:
                    pass
            if detector is not None and detection_session_key is not None:
                detector.forget(detection_session_key)

    def _camera_worker(self, camera_id: str, stream: CameraStream, stop_event: threading.Event):
        """
        Background worker reading frames, creating FramePackets, and dispatching to AI pipeline.
        Conforms to Rule 13 (camera isolation) and Rule 14 (subsampled frame dispatching).
        """
        logger.info(f"[{camera_id}] Ingestion worker active.")
        process_every_n = max(1, int(getattr(settings, "PROCESS_EVERY_N_FRAMES", 1)))
        connect_delay = 2.0
        next_connect_at = 0.0

        while not stop_event.is_set():
            with self._lock:
                if self._streams.get(camera_id) is not stream:
                    # Source was replaced while this worker was connecting.
                    return

            # Opening RTSP/HLS can block while a gateway is unavailable. Do it
            # in this worker (never an API request), with a bounded exponential
            # retry rather than a tight open/fail loop.
            if stream.state == CameraState.OFFLINE:
                now = time.monotonic()
                if now < next_connect_at:
                    stop_event.wait(timeout=min(0.25, next_connect_at - now))
                    continue
                if stream.connect():
                    connect_delay = 2.0
                    next_connect_at = 0.0
                else:
                    next_connect_at = time.monotonic() + connect_delay
                    logger.warning(
                        "[%s] Initial connection unavailable; retrying in %.1fs",
                        camera_id,
                        connect_delay,
                    )
                    connect_delay = min(connect_delay * 2.0, 30.0)
                continue

            try:
                start_time = time.monotonic()
                packet = stream.read_packet(stop_event=stop_event)

                if packet is not None:
                    with self._lock:
                        if self._streams.get(camera_id) is not stream:
                            # A replacement worker owns this camera now; never
                            # publish a stale packet into its fresh timeline.
                            return
                        self._latest_packets[camera_id] = packet

                        # If no annotated frame is present yet, mirror raw frame
                        if camera_id not in self._latest_annotated_frames:
                            self._latest_annotated_frames[camera_id] = packet.frame

                    # Rule 14: Subsample frames while strictly preserving packet PTS
                    if packet.sequence_number % process_every_n == 0:
                        with self._lock:
                            if self._streams.get(camera_id) is not stream:
                                return
                            callback = self._pipeline_callback
                        if callback is not None:
                            try:
                                callback(packet)
                            except Exception as cb_err:
                                from ..services.sentinel_stream_service import redact_text

                                logger.error(
                                    "[%s] Error in AI pipeline callback: %s",
                                    camera_id,
                                    redact_text(cb_err),
                                )

                else:
                    # No frame returned (transient slip or reconnecting)
                    time.sleep(0.05)

                # Pace loop according to nominal rate
                elapsed = time.monotonic() - start_time
                target_interval = 1.0 / max(stream.nominal_fps, 10.0)
                sleep_time = max(0.001, target_interval - elapsed)
                time.sleep(sleep_time)

            except Exception as e:
                # Rule 13: Top-level exception isolation. Decoder errors can
                # echo their input URL, so scrub them before logging/API state.
                from ..services.sentinel_stream_service import redact_text

                logger.error("[%s] Unexpected error in camera worker: %s", camera_id, redact_text(e))
                time.sleep(0.5)

        logger.info(f"[{camera_id}] Ingestion worker terminated.")


# Global singleton instance
camera_manager = CameraManager()
