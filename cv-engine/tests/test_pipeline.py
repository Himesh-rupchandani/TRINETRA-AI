"""CameraPipeline with fake tracker/OCR: one sighting, not N duplicates."""

from __future__ import annotations

import numpy as np

from anpr.ocr import OcrEngine, OcrReading
from capture.frames import FramePacket
from config.settings import load_settings
from capture.sentinel_catalogue import Camera
from integration.backend_client import BackendClient
from pipeline import CameraPipeline
from tracking.vehicle_tracker import TrackedVehicle


class FakeOcr(OcrEngine):
    def recognize(self, crop):
        if crop is None or crop.size == 0:
            return []
        return [OcrReading("GJ01AB1234", 0.9)]


class FakeTracker:
    def __init__(self):
        self.updates = 0
        self.resets = 0

    def update(self, frame, camera_id, pts_ms, continuous_ms):
        self.updates += 1
        h, w = frame.shape[:2]
        return [
            TrackedVehicle(
                track_id=17,
                bbox=(0, 0, w, h),
                class_name="car",
                confidence=0.9,
                camera_id=camera_id,
                pts_ms=pts_ms,
                continuous_ms=continuous_ms,
                first_seen_pts_ms=0.0,
            )
        ]

    def reset(self, reason=""):
        self.resets += 1


def _packet(seq, pts):
    return FramePacket(
        frame=(np.random.rand(64, 96, 3) * 200).astype(np.uint8),
        camera_id="cam04",
        pts_ms=pts,
        continuous_ms=pts,
        seq=seq,
    )


def _settings(tmp_path):
    return load_settings(
        env={},
        anpr_interval_s=0.0,
        frame_skip=0,
        inference_interval_s=0.0,
        evidence_dir=str(tmp_path / "ev"),
        dead_letter_path=str(tmp_path / "dl.jsonl"),
    )


class RecordingSession:
    def __init__(self):
        self.posted = []

    def post(self, url, json=None, timeout=None):
        self.posted.append(json)

        class R:
            status_code = 200

        return R()


def test_many_frames_yield_exactly_one_sighting(tmp_path):
    settings = _settings(tmp_path)
    session = RecordingSession()
    backend = BackendClient(settings, session=session)  # worker not started
    tracker = FakeTracker()
    pipeline = CameraPipeline(settings, Camera(camera_id="cam04"), tracker=tracker, ocr_engine=FakeOcr(), backend=backend)

    emitted = []
    for seq in range(6):
        emitted += pipeline.process_packet(_packet(seq + 1, seq * 1000.0))

    events = [e for e in emitted if e is not None]
    assert len(events) == 1, f"expected one sighting, got {len(events)}"
    event = events[0]
    assert event.plate == "GJ01AB1234"
    assert event.track_id == 17
    assert event.evidence_ref is not None
    # The event was queued for the backend exactly once.
    assert backend.pending == 1


def test_different_tracks_are_not_merged(tmp_path):
    settings = _settings(tmp_path)
    backend = BackendClient(settings, session=RecordingSession())
    tracker = FakeTracker()

    class TwoTracks(FakeTracker):
        def update(self, frame, camera_id, pts_ms, continuous_ms):
            t = super().update(frame, camera_id, pts_ms, continuous_ms)
            second = TrackedVehicle(
                track_id=18, bbox=(0, 0, 10, 10), class_name="bus", confidence=0.8,
                camera_id=camera_id, pts_ms=pts_ms, continuous_ms=continuous_ms,
                first_seen_pts_ms=0.0,
            )
            return t + [second]

    pipeline = CameraPipeline(settings, Camera(camera_id="cam04"), tracker=TwoTracks(), ocr_engine=FakeOcr(), backend=backend)
    emitted = []
    for seq in range(6):
        emitted += pipeline.process_packet(_packet(seq + 1, seq * 1000.0))
    ids = {e.track_id for e in emitted if e}
    assert ids == {17, 18}  # two distinct vehicles, one sighting each


def test_hard_scene_cut_resets_tracking(tmp_path):
    settings = _settings(tmp_path)
    settings.scene_cut_threshold = 0.4
    tracker = FakeTracker()
    pipeline = CameraPipeline(settings, Camera(camera_id="cam04"), tracker=tracker, ocr_engine=FakeOcr())

    black = np.zeros((64, 96, 3), np.uint8)
    white = np.full((64, 96, 3), 255, np.uint8)

    # Feed a short stable run so the cut detector has a baseline and its
    # anti-flap counter, then a hard change on the next frame.
    for seq in range(5):
        pipeline.process_packet(FramePacket(frame=black, camera_id="cam04", pts_ms=seq * 40.0, continuous_ms=seq * 40.0, seq=seq + 1))
    assert tracker.updates == 5
    pipeline.process_packet(FramePacket(frame=white, camera_id="cam04", pts_ms=200.0, continuous_ms=200.0, seq=6))
    # The cut frame must not be tracked; the tracker was reset instead.
    assert tracker.resets >= 1
    assert tracker.updates == 5
