"""RTSP capture — the transport Sentinel intends for AI inference.

Non-negotiables from the Sentinel guidance:

* **RTSP over TCP.** Interleaved TCP avoids the UDP packet loss that turns into
  grey/green macroblocking and wrecks ANPR. Enforced here at two levels: the
  ``OPENCV_FFMPEG_CAPTURE_OPTIONS`` environment variable for the OpenCV backend
  and ``rtsp_transport=tcp`` for the PyAV backend.
* **PTS for timing**, never frame arrival time, never ``CAP_PROP_FPS``.
* Decoder "join" warnings are not fatal — a warning is logged and the frame
  that did decode is still used.
"""

from __future__ import annotations

import logging

from capture.sentinel_catalogue import Camera
from capture.stream_capture import OpenCVStreamCapture, PyAVStreamCapture
from config.settings import Settings
from logging_setup import log_event

log = logging.getLogger("trinetra.capture.rtsp")

#: Forced onto every RTSP open. ``nobuffer``/``low_delay`` keep latency down;
#: they do not affect timing because timing comes from PTS.
RTSP_FFMPEG_OPTIONS = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;500000"


class RtspCapture(OpenCVStreamCapture):
    """OpenCV/FFmpeg RTSP capture over TCP."""

    source = "rtsp"
    ffmpeg_options = RTSP_FFMPEG_OPTIONS


class RtspPyAVCapture(PyAVStreamCapture):
    """PyAV RTSP capture — true demuxer PTS, TCP transport."""

    source = "rtsp"


def open_rtsp(camera: Camera, settings: Settings) -> RtspCapture | RtspPyAVCapture:
    """Build (not yet open) the best available RTSP capture for ``camera``.

    ``CAPTURE_BACKEND``: ``auto`` (PyAV when installed, else OpenCV),
    ``opencv`` or ``pyav``.
    """
    choice = (settings.capture_backend or "auto").lower()
    if choice in ("auto", "pyav"):
        if RtspPyAVCapture.available():
            return RtspPyAVCapture(camera, settings)
        if choice == "pyav":
            log_event(
                log,
                "capture_backend_unavailable",
                level=logging.WARNING,
                backend="pyav",
                fallback="opencv",
            )
    return RtspCapture(camera, settings)
