"""
HLS capture — used as a remote-friendly protocol and as fallback when RTSP
cannot be opened (spec §8).
"""
from __future__ import annotations

import logging

from .stream_capture import StreamCaptureBase

logger = logging.getLogger("cv_engine.capture")


class HLSCapture(StreamCaptureBase):
    source_type = "hls"

    def _capture_kwargs(self) -> dict:
        # Keep HLS segment reads bounded; http_persistent off avoids keeping
        # long-lived connections that some proxies drop.
        return {"timeout": int(self.read_timeout_sec * 1_000_000)}


def open_with_fallback(camera, transport: str = "tcp", allow_hls_fallback: bool = True, **kwargs):
    """
    Try RTSP first (preferred for inference); fall back to HLS when RTSP is
    unreachable and the camera advertises an HLS URL. Returns (capture, ok).
    """
    from .rtsp_capture import RTSPCapture
    from .hls_capture import HLSCapture

    capture = None
    if camera.rtsp_url:
        capture = RTSPCapture(camera.camera_id, camera.rtsp_url, transport=transport, **kwargs)
        if capture.open():
            return capture, True
        logger.warning(
            "[%s] RTSP unavailable (%s)%s",
            camera.camera_id,
            capture.last_error,
            " — trying HLS fallback" if (allow_hls_fallback and camera.hls_url) else "",
        )

    if allow_hls_fallback and camera.hls_url:
        capture = HLSCapture(camera.camera_id, camera.hls_url, **kwargs)
        if capture.open():
            return capture, True

    if capture is None and camera.hls_url:
        capture = HLSCapture(camera.camera_id, camera.hls_url, **kwargs)

    return capture, False
