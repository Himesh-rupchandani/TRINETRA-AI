"""
RTSP capture (spec §8): forces RTSP over TCP via FFmpeg options.

RTSP is the preferred protocol for AI inference on Sentinel feeds.
"""
from __future__ import annotations

import logging

from .stream_capture import StreamCaptureBase

logger = logging.getLogger("cv_engine.capture")


class RTSPCapture(StreamCaptureBase):
    source_type = "rtsp"

    def __init__(self, camera_id: str, url: str, transport: str = "tcp", **kwargs):
        super().__init__(camera_id, url, **kwargs)
        self.transport = transport.lower()

    def _capture_kwargs(self) -> dict:
        # Force the RTSP transport (TCP by Sentinel guidance) and bound the
        # socket I/O timeout so reads cannot hang forever on a dead feed.
        return {
            "rtsp_transport": self.transport,
            "stimeout": int(self.read_timeout_sec * 1_000_000),  # microseconds
        }
