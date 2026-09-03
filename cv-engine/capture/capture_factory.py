"""Choosing and opening a capture for a camera.

Precedence: ``settings.preferred_transport`` (RTSP by default, per Sentinel
guidance), then HLS if ``ALLOW_HLS_FALLBACK`` is on and the catalogue publishes
an HLS URL. Which transport actually produced the frames is recorded on the
packet (``source``) and in the metrics, so no number is ever reported without
its transport.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from capture.frames import FramePacket
from capture.hls_capture import open_hls
from capture.rtsp_capture import open_rtsp
from capture.sentinel_catalogue import Camera
from capture.stream_capture import StreamCapture
from config.settings import Settings
from logging_setup import log_event

log = logging.getLogger("trinetra.capture")


class FallbackCapture(StreamCapture):
    """Tries the preferred transport, then the fallback, exposing one as a whole.

    Deliberately *not* magic: :attr:`active_source` and the packet ``source``
    field always tell you which transport is really feeding the pipeline.
    """

    source = "fallback"

    def __init__(self, camera: Camera, settings: Settings) -> None:
        super().__init__(camera, settings)
        self._candidates: list[StreamCapture] = []
        self._active: Optional[StreamCapture] = None
        preferred = (settings.preferred_transport or "rtsp").lower()
        secondary = "hls" if preferred == "rtsp" else "rtsp"
        order = [preferred]
        if settings.allow_hls_fallback and secondary == "hls":
            order.append("hls")
        for transport in order:
            if transport == "rtsp" and camera.rtsp_url:
                self._candidates.append(open_rtsp(camera, settings))
            elif transport == "hls" and camera.hls_url:
                self._candidates.append(open_hls(camera, settings))

    @property
    def active_source(self) -> str | None:
        return self._active.source if self._active else None

    def open(self) -> bool:
        for candidate in self._candidates:
            if candidate.open():
                self._active = candidate
                self.source = candidate.source
                self.stats = candidate.stats
                self.timeline = candidate.timeline
                return True
            log_event(
                log,
                "transport_open_failed",
                level=logging.WARNING,
                camera=self.camera.camera_id,
                transport=candidate.source,
            )
        return False

    def read(self) -> Optional[FramePacket]:
        return self._active.read() if self._active else None

    def close(self) -> None:
        if self._active is not None:
            self._active.close()
            self._active = None


def build_capture(camera: Camera, settings: Settings, transport: str | None = None) -> StreamCapture:
    """Build one unopened capture for an explicit transport."""
    transport = (transport or settings.preferred_transport or "rtsp").lower()
    if transport == "hls":
        return open_hls(camera, settings)
    return open_rtsp(camera, settings)


def make_capture_factory(camera: Camera, settings: Settings) -> Callable[[], StreamCapture]:
    """Zero-arg factory for :class:`capture.reconnect.ReconnectingCapture`.

    A fresh capture object per attempt is required: a decoder that has lost its
    stream cannot be revived by calling ``open()`` again.
    """

    def factory() -> StreamCapture:
        if len({camera.rtsp_url, camera.hls_url} - {None}) > 1 and settings.allow_hls_fallback:
            return FallbackCapture(camera, settings)
        return build_capture(camera, settings)

    return factory


def open_capture(camera: Camera, settings: Settings) -> tuple[StreamCapture | None, str]:
    """Open a capture now. Returns ``(capture, error_message)``.

    Used by one-shot probe/benchmark scripts, which want a single answer rather
    than an endless reconnect loop.
    """
    capture = make_capture_factory(camera, settings)()
    if capture.open():
        log_event(
            log,
            "capture_ready",
            camera=camera.camera_id,
            transport=getattr(capture, "active_source", None) or capture.source,
        )
        return capture, ""
    return None, f"could not open {camera.camera_id} over {settings.preferred_transport}"
