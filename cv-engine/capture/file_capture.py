"""File capture — DEMO MODE source, and the capture test harness.

Reads a stored recording (or a single image repeated) through exactly the same
``StreamCapture`` interface as RTSP/HLS, so the rest of the pipeline cannot tell
the difference. Packets are tagged ``source="file"`` so a demo frame is never
mistaken for live government footage in logs, metrics or evidence.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from capture.frames import FramePacket
from capture.stream_capture import OpenCVStreamCapture
from config.settings import Settings
from logging_setup import log_event

log = logging.getLogger("trinetra.capture.file")


class FileCapture(OpenCVStreamCapture):
    """Replays a video file. PTS comes from the container, as with a live feed."""

    source = "file"
    ffmpeg_options = ""

    def __init__(self, path: str | Path, settings: Settings, camera_id: str = "demo", fps_hint: float | None = None) -> None:
        from capture.sentinel_catalogue import Camera

        camera = Camera(camera_id=camera_id, name=f"file:{Path(path).name}", fps=fps_hint)
        self._path = str(path)
        super().__init__(camera, settings)

    def url(self) -> str | None:
        return self._path if Path(self._path).exists() else None


class SyntheticFrameCapture:
    """Deterministic synthetic frames — no video file, no decoder needed.

    Used by ``scripts/run_demo.py`` and by the CI integration test so the full
    detection → tracking → ANPR → event → POST path can be exercised without a
    Sentinel connection. Packets are tagged ``source="synthetic"``.
    """

    source = "synthetic"

    def __init__(
        self,
        frames: list[np.ndarray],
        camera_id: str = "demo",
        interval_ms: float = 40.0,
        settings: Settings | None = None,
    ) -> None:
        from capture.sentinel_catalogue import Camera

        self.camera = Camera(camera_id=camera_id, name="synthetic")
        self._frames = frames
        self._interval_ms = interval_ms
        self._index = 0
        self._pts_ms = 0.0
        self.settings = settings
        self.stats = None
        log_event(log, "synthetic_capture_created", camera=camera_id, frames=len(frames))

    def open(self) -> bool:
        return bool(self._frames)

    def read(self) -> FramePacket | None:
        if self._index >= len(self._frames):
            return None
        frame = self._frames[self._index]
        self._index += 1
        packet = FramePacket(
            frame=frame,
            camera_id=self.camera.camera_id,
            pts_ms=self._pts_ms,
            continuous_ms=self._pts_ms,
            source=self.source,
            seq=self._index,
        )
        self._pts_ms += self._interval_ms
        return packet

    def close(self) -> None:
        self._index = 0
        self._pts_ms = 0.0


def write_test_video(
    path: str | Path, frame_count: int = 30, fps: float = 25.0, size: tuple[int, int] = (320, 240)
) -> Path:
    """Write a small deterministic mp4 (used by tests and demo fixtures)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    if not writer.isOpened():  # pragma: no cover - codec availability
        raise RuntimeError("could not open VideoWriter (mp4v) for the test fixture")
    for i in range(frame_count):
        frame = np.full((size[1], size[0], 3), 20, np.uint8)
        x = int(10 + (size[0] - 60) * (i / max(frame_count - 1, 1)))
        cv2.rectangle(frame, (x, 80), (x + 50, 160), (200, 180, 60), -1)
        cv2.putText(frame, str(i), (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        writer.write(frame)
    writer.release()
    return path
