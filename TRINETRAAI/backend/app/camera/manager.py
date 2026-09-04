import os
import sys
from pathlib import Path
import threading
import time
from typing import Dict, List, Optional, Callable
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
        label = "RECORDED DEMO FOOTAGE - NOT LIVE" if is_file else "LIVE SOURCE"
        h, w = frame.shape[:2]
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        x2, y2 = w - 10, h - 12
        cv2.rectangle(frame, (x2 - tw - 10, y2 - th - 8), (x2 + 2, y2 + 4), (15, 18, 24), -1)
        color = (0, 200, 255) if is_file else (0, 255, 0)
        cv2.putText(frame, label, (x2 - tw - 5, y2), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, color, 1, cv2.LINE_AA)
        return frame

    @staticmethod
    def _read_ondemand_frame(cap: "cv2.VideoCapture", source: str):
        """Read one frame for an on-demand live view, looping the file safely."""
        ok, frame = cap.read()
        if not (ok and frame is not None and frame.size > 0):
            # Some containers cannot seek backwards reliably — reopen instead.
            try:
                cap.release()
            except Exception:
                pass
            cap.open(source)
            ok, frame = cap.read()
        if not (ok and frame is not None and frame.size > 0):
            return None
        h, w = frame.shape[:2]
        if w > 1280:  # keep on-demand views cheap to decode and stream
            scale = 1280.0 / w
            frame = cv2.resize(frame, (1280, int(round(h * scale))), interpolation=cv2.INTER_AREA)
        return frame

    def generate_mjpeg_stream(self, camera_id: str):
        """Yield multipart MJPEG stream frames for HTTP live view.

        When no resident worker is running for the camera (e.g. file-backed
        demo cameras with AUTO_START_CAMERAS off), the source file is decoded
        on demand for the lifetime of this HTTP connection only.
        """
        ondemand_cap = None
        ondemand_source = None
        ondemand_is_file = True
        try:
            while True:
                frame = self.get_latest_frame(camera_id, annotated=True)
                if frame is None:
                    frame = self.get_latest_frame(camera_id.upper(), annotated=True)
                if frame is None and ondemand_source is None and ondemand_cap is None:
                    resolved = self._ondemand_source(camera_id)
                    if resolved is not None:
                        ondemand_source, ondemand_is_file = resolved
                        ondemand_cap = cv2.VideoCapture(ondemand_source)
                        kind = "local recording" if ondemand_is_file else "real network stream"
                        logger.info(
                            f"[{camera_id.upper()}] On-demand live view decoding {kind}: {ondemand_source}"
                        )
                if frame is None and ondemand_cap is not None:
                    frame = self._read_ondemand_frame(ondemand_cap, ondemand_source)
                    if frame is not None:
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
                time.sleep(0.08)  # ~12 FPS on-demand live preview pacing
        finally:
            if ondemand_cap is not None:
                try:
                    ondemand_cap.release()
                except Exception:
                    pass

    def _camera_worker(self, camera_id: str, stream: CameraStream, stop_event: threading.Event):
        """
        Background worker reading frames, creating FramePackets, and dispatching to AI pipeline.
        Conforms to Rule 13 (camera isolation) and Rule 14 (subsampled frame dispatching).
        """
        logger.info(f"[{camera_id}] Ingestion worker active.")
        process_every_n = getattr(settings, "PROCESS_EVERY_N_FRAMES", 1)

        while not stop_event.is_set():
            try:
                start_time = time.monotonic()
                packet = stream.read_packet()

                if packet is not None:
                    with self._lock:
                        self._latest_packets[camera_id] = packet

                        # If no annotated frame is present yet, mirror raw frame
                        if camera_id not in self._latest_annotated_frames:
                            self._latest_annotated_frames[camera_id] = packet.frame

                    # Rule 14: Subsample frames while strictly preserving packet PTS
                    if packet.sequence_number % process_every_n == 0:
                        callback = self._pipeline_callback
                        if callback is not None:
                            try:
                                callback(packet)
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
