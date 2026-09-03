"""Capture backends.

Two backends share one interface:

* :class:`OpenCVStreamCapture` — OpenCV/FFmpeg. Always available, handles both
  RTSP (forced to TCP) and HLS.
* :class:`PyAVStreamCapture` — PyAV. Optional (``pip install av``), but it
  exposes the *true* packet PTS and per-stream codec info, which is what we
  want for measurement work.

Both attach stream PTS to every packet and both refuse to fall back to
wall-clock timing (see :mod:`capture.frames`).
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from capture.frames import STATE_ERROR, STATE_OK, FramePacket, PtsTimeline, nominal_interval_from_fps
from capture.sentinel_catalogue import Camera
from config.settings import Settings
from logging_setup import log_event

log = logging.getLogger("trinetra.capture")

try:  # OpenCV is a hard dependency, but keep the failure message actionable.
    import cv2
except ImportError as exc:  # pragma: no cover
    raise ImportError("opencv-python-headless is required (pip install opencv-python-headless)") from exc


@dataclass
class CaptureStats:
    """Measured, not assumed. ``delivered_fps`` comes from PTS deltas."""

    frames_read: int = 0
    decode_failures: int = 0
    opened_at: float | None = None
    last_pts_ms: float = 0.0
    delivered_fps: float = 0.0
    avg_decode_ms: float = 0.0
    loops_detected: int = 0
    width: int = 0
    height: int = 0
    codec: str | None = None
    extras: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        data = {k: v for k, v in self.__dict__.items() if k != "extras"}
        data.update(self.extras)
        return data


class StreamCapture:
    """Interface every backend implements."""

    source = "unknown"

    def __init__(self, camera: Camera, settings: Settings) -> None:
        self.camera = camera
        self.settings = settings
        self.stats = CaptureStats()
        self.timeline = PtsTimeline(
            nominal_interval_from_fps(camera.fps, default_ms=40.0)
        )
        self._seq = 0
        self._first_continuous: float | None = None

    # -- lifecycle ----------------------------------------------------------
    def open(self) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def read(self) -> Optional[FramePacket]:  # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    # -- helpers ------------------------------------------------------------
    def url(self) -> str | None:
        """URL for this capture's transport. Resolved lazily (see ``open``)."""
        return self.camera.stream_url(self.source)

    def _make_packet(
        self, frame: np.ndarray, raw_pts_ms: float | None, decode_ms: float, state: str = STATE_OK
    ) -> FramePacket:
        continuous, _delta, valid, discontinuity = self.timeline.update(raw_pts_ms)
        self._seq += 1
        self.stats.frames_read += 1
        self.stats.last_pts_ms = continuous
        self.stats.loops_detected = self.timeline.loops
        self.stats.width, self.stats.height = int(frame.shape[1]), int(frame.shape[0])
        n = self.stats.frames_read
        self.stats.avg_decode_ms = (
            self.stats.avg_decode_ms * (n - 1) + decode_ms
        ) / n
        if valid:
            if self._first_continuous is None:
                self._first_continuous = continuous
            elapsed_s = (continuous - self._first_continuous) / 1000.0
            if elapsed_s > 0.2:
                self.stats.delivered_fps = round((self.stats.frames_read - 1) / elapsed_s, 2)
        packet = FramePacket(
            frame=frame,
            camera_id=self.camera.camera_id,
            pts_ms=float(raw_pts_ms) if raw_pts_ms is not None else float("nan"),
            continuous_ms=continuous,
            capture_state=state,
            source=self.source,
            seq=self._seq,
            decode_ms=decode_ms,
            pts_valid=valid,
            scene_cut=discontinuity,
        )
        return packet

    def _note_failure(self, reason: str) -> None:
        self.stats.decode_failures += 1
        log_event(
            log,
            "frame_decode_failure",
            level=logging.DEBUG,
            camera=self.camera.camera_id,
            reason=reason,
            total=self.stats.decode_failures,
        )


class OpenCVStreamCapture(StreamCapture):
    """OpenCV/FFmpeg capture. Subclasses pick the URL and transport."""

    source = "rtsp"
    #: FFmpeg options appended via OPENCV_FFMPEG_CAPTURE_OPTIONS.
    ffmpeg_options: str = ""

    def __init__(self, camera: Camera, settings: Settings) -> None:
        super().__init__(camera, settings)
        self._cap: Optional[cv2.VideoCapture] = None
        # NOTE: the URL is resolved in open(), not here, so that subclasses may
        # set their own attributes before the first resolution.
        self._url: Optional[str] = None

    def _open_timeout_params(self) -> list:
        open_ms = int(self.settings.capture_open_timeout_s * 1000)
        read_ms = int(self.settings.read_timeout_s * 1000)
        params: list = []
        for prop, value in (
            (getattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC", None), open_ms),
            (getattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC", None), read_ms),
        ):
            if prop is not None:
                params.extend([prop, value])
        return params

    # -- lifecycle ----------------------------------------------------------
    def open(self) -> bool:
        self._url = self.url()
        if not self._url:
            log_event(
                log,
                "capture_no_url",
                level=logging.ERROR,
                camera=self.camera.camera_id,
                source=self.source,
            )
            return False
        previous_options = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS")
        if self.ffmpeg_options:
            merged = (
                f"{previous_options}|{self.ffmpeg_options}"
                if previous_options
                else self.ffmpeg_options
            )
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = merged
        started = time.perf_counter()
        try:
            params = self._open_timeout_params()
            self._cap = (
                cv2.VideoCapture(self._url, cv2.CAP_FFMPEG, params)
                if params
                else cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
            )
        except Exception as exc:  # noqa: BLE001
            log_event(
                log,
                "capture_open_error",
                level=logging.ERROR,
                camera=self.camera.camera_id,
                error=f"{type(exc).__name__}: {exc}",
            )
            return False
        finally:
            # Restore, never clobber: FFmpeg reads the variable at open time only.
            if previous_options is None:
                os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
            else:
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = previous_options

        opened = bool(self._cap and self._cap.isOpened())
        took_ms = (time.perf_counter() - started) * 1000
        if not opened:
            self._note_failure(f"VideoCapture did not open ({took_ms:.0f} ms)")
            return False

        self.stats.opened_at = time.monotonic()
        self.timeline.reset()
        # Reported FPS is recorded for the record only — never used for timing.
        reported_fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 0.0)
        self.stats.extras["reported_fps_untrusted"] = round(reported_fps, 2)
        self.stats.extras["backend_fourcc"] = _fourcc_name(self._cap.get(cv2.CAP_PROP_FOURCC))
        log_event(
            log,
            "capture_opened",
            camera=self.camera.camera_id,
            source=self.source,
            open_ms=took_ms,
            reported_fps_untrusted=reported_fps,
            width=int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
            height=int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
        )
        return True

    def read(self) -> Optional[FramePacket]:
        if self._cap is None:
            return None
        started = time.perf_counter()
        ok, frame = self._cap.read()
        decode_ms = (time.perf_counter() - started) * 1000
        if not ok or frame is None:
            self._note_failure("cv2 read returned no frame")
            return None
        raw_pts = self._cap.get(cv2.CAP_PROP_POS_MSEC)
        return self._make_packet(frame, raw_pts, decode_ms)

    def close(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            finally:
                self._cap = None


class PyAVStreamCapture(StreamCapture):
    """PyAV backend — real packet PTS, explicit TCP transport, per-stream info.

    Used when ``av`` is installed and ``CAPTURE_BACKEND`` allows it. Preferred
    for measurement runs because PTS comes straight from the demuxer instead of
    from OpenCV's ``CAP_PROP_POS_MSEC`` approximation.
    """

    source = "rtsp"

    def __init__(self, camera: Camera, settings: Settings) -> None:
        super().__init__(camera, settings)
        self._container = None
        self._stream = None
        self._url: Optional[str] = None

    @staticmethod
    def available() -> bool:
        try:
            import av  # noqa: F401

            return True
        except ImportError:
            return False

    def open(self) -> bool:
        self._url = self.url()
        if not self._url:
            return False
        try:
            import av
        except ImportError:
            log_event(log, "capture_backend_unavailable", level=logging.ERROR, backend="pyav")
            return False

        timeout_us = int(self.settings.read_timeout_s * 1_000_000)
        options = {
            "rtsp_transport": "tcp",
            "stimeout": str(timeout_us),
            "fflags": "nobuffer",
            "flags": "low_delay",
        }
        if self.source == "hls":
            options = {"http_persistent": "1"}
        started = time.perf_counter()
        try:
            self._container = av.open(
                self._url,
                options=options,
                timeout=(self.settings.capture_open_timeout_s, self.settings.read_timeout_s),
            )
            self._stream = self._container.streams.video[0]
            self._stream.thread_type = "AUTO"
        except Exception as exc:  # noqa: BLE001
            self._note_failure(f"{type(exc).__name__}: {exc}")
            return False

        self.stats.opened_at = time.monotonic()
        self.timeline.reset()
        codec = getattr(self._stream.codec_context, "name", None)
        self.stats.codec = codec
        self.stats.extras["pyav_time_base"] = str(getattr(self._stream, "time_base", None))
        log_event(
            log,
            "capture_opened",
            camera=self.camera.camera_id,
            source=self.source,
            backend="pyav",
            codec=codec,
            open_ms=(time.perf_counter() - started) * 1000,
            width=self._stream.codec_context.width,
            height=self._stream.codec_context.height,
        )
        return True

    def read(self) -> Optional[FramePacket]:
        if self._container is None or self._stream is None:
            return None
        started = time.perf_counter()
        try:
            frame = next(self._container.decode(self._stream))
        except StopIteration:
            self._note_failure("end of stream")
            return None
        except Exception as exc:  # noqa: BLE001
            self._note_failure(f"{type(exc).__name__}: {exc}")
            return None
        decode_ms = (time.perf_counter() - started) * 1000
        image = frame.to_ndarray(format="bgr24")
        raw_pts_ms = self._pts_ms(frame)
        return self._make_packet(image, raw_pts_ms, decode_ms)

    def _pts_ms(self, frame) -> float | None:
        pts = getattr(frame, "pts", None)
        if pts is None:
            return None
        time_base = getattr(self._stream, "time_base", None)
        if time_base is None:
            return float(pts)
        try:
            return float(pts * time_base * 1000.0)
        except (TypeError, ValueError):  # pragma: no cover
            return None

    def close(self) -> None:
        if self._container is not None:
            try:
                self._container.close()
            finally:
                self._container = None
                self._stream = None


def _fourcc_name(value: float) -> str | None:
    try:
        code = int(value)
    except (TypeError, ValueError):
        return None
    if code <= 0:
        return None
    return "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4)).strip() or None


def backend_available(name: str) -> bool:
    if name == "pyav":
        return PyAVStreamCapture.available()
    if name == "opencv":
        return True
    return False
