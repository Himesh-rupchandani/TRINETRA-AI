"""HLS capture — the remote/browser-friendly transport.

HLS is the *fallback*, used when RTSP cannot be opened (blocked port 8554,
NAT, a viewer running off-network). It carries real latency — segments are
typically 2–6 s long — so it is fine for "is the camera alive / what does the
scene look like" and acceptable for detection demos, but any latency-sensitive
measurement should say which transport produced the number.

PTS handling is identical to RTSP: the value comes from the segments, not from
the wall clock.
"""

from __future__ import annotations

import logging

from capture.sentinel_catalogue import Camera
from capture.stream_capture import OpenCVStreamCapture, PyAVStreamCapture
from config.settings import Settings
from logging_setup import log_event

log = logging.getLogger("trinetra.capture.hls")

HLS_FFMPEG_OPTIONS = "http_persistent;1|reconnect;1|reconnect_streamed;1"


class HlsCapture(OpenCVStreamCapture):
    """OpenCV/FFmpeg HLS (m3u8) capture."""

    source = "hls"
    ffmpeg_options = HLS_FFMPEG_OPTIONS


class HlsPyAVCapture(PyAVStreamCapture):
    """PyAV HLS capture."""

    source = "hls"


def open_hls(camera: Camera, settings: Settings) -> HlsCapture | HlsPyAVCapture:
    """Build (not yet open) the best available HLS capture for ``camera``."""
    choice = (settings.capture_backend or "auto").lower()
    if choice in ("auto", "pyav") and HlsPyAVCapture.available():
        return HlsPyAVCapture(camera, settings)
    if choice == "pyav":
        log_event(
            log, "capture_backend_unavailable", level=logging.WARNING, backend="pyav", fallback="opencv"
        )
    return HlsCapture(camera, settings)
