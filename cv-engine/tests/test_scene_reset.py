"""
Scene discontinuity handling (spec §14) at pipeline level.

Sentinel feeds loop; a hard cut must reset tracking/plate state instead of
carrying invalid long-lived tracks. Uses scripted packets (no live feed).
"""
import numpy as np

from capture.frame_packet import CaptureState, FramePacket
from capture.sentinel_catalogue import Camera
from config.settings import Settings
from detection.vehicle_detector import Detection
from pipeline.camera_pipeline import CameraPipeline


class FixedDetector:
    """Returns the detections queued for the next frame."""

    def __init__(self):
        self.queue = []

    def detect(self, frame, camera_id=None, pts_ms=None):
        out = self.queue.pop(0) if self.queue else []
        for d in out:
            d.camera_id = camera_id
            d.pts_ms = pts_ms
        return out


class NullOcr:
    def read(self, image):
        return []


class RecordingBackend:
    def __init__(self):
        self.events = []

    def submit(self, event):
        self.events.append(event)
        return True


def _packet(pts, seq, disc=False):
    return FramePacket(
        frame=np.zeros((240, 320, 3), dtype=np.uint8),
        camera_id="cam04",
        pts_ms=pts,
        capture_state=CaptureState.ONLINE,
        sequence_number=seq,
        is_discontinuity=disc,
    )


def _det(x=100):
    return Detection(bbox=[x, 100, x + 60, 180], class_name="car", confidence=0.9)


def make_pipeline(settings=None):
    settings = settings or Settings(anpr_enabled=False, frame_skip=1)
    camera = Camera(camera_id="cam04", latitude=23.0, longitude=72.5)
    detector = FixedDetector()
    backend = RecordingBackend()
    pipeline = CameraPipeline(
        camera, settings,
        detector=detector,
        ocr_engine=NullOcr(),
        backend_client=backend,
        evidence_writer=None,
    )
    return pipeline, detector, backend


def test_discontinuity_resets_track_ids():
    pipeline, detector, backend = make_pipeline()

    detector.queue = [[_det(100)], [_det(104)], [], [], [], []]
    p1 = pipeline.process_packet(_packet(0.0, 1))
    p2 = pipeline.process_packet(_packet(40.0, 2))
    first_ids = {t.track_id for t in pipeline.tracker.update([], pts_ms=80.0)}

    # Hard scene cut: same box appears, but identity must be NEW.
    detector.queue = [[_det(100)], [_det(104)]]
    pipeline.process_packet(_packet(80.0, 3, disc=True))
    pipeline.process_packet(_packet(120.0, 4))
    second_ids = {t.track_id for t in pipeline.tracker.update([], pts_ms=160.0)}

    assert pipeline.stats.discontinuities >= 1
    assert first_ids and second_ids
    assert first_ids.isdisjoint(second_ids), "track ids must not survive a scene cut"


def test_discontinuity_clears_plate_memory_and_dedup():
    settings = Settings(anpr_enabled=False)
    pipeline, detector, _ = make_pipeline(settings)

    from anpr.confidence import PlateReading
    pipeline.plate_memory.add_reading(7, PlateReading("GJ 01 AB-1234", "GJ01AB1234", 0.9))
    pipeline.dedup.should_emit("cam04", 7, "GJ01AB1234", pts_ms=0.0)

    detector.queue = [[]]
    pipeline.process_packet(_packet(100.0, 1, disc=True))

    assert pipeline.plate_memory.best(7) is None
    # dedup state cleared -> same key can emit again immediately
    assert pipeline.dedup.should_emit("cam04", 7, "GJ01AB1234", pts_ms=1.0)


def test_normal_gap_does_not_reset():
    """A short decode gap (no discontinuity flag) must keep track identity."""
    pipeline, detector, _ = make_pipeline()
    detector.queue = [[_det(100)], [], [_det(104)], [_det(108)]]
    pipeline.process_packet(_packet(0.0, 1))
    pipeline.process_packet(_packet(40.0, 2))  # no detection (gap)
    pipeline.process_packet(_packet(80.0, 3))
    pipeline.process_packet(_packet(120.0, 4))
    tracks = pipeline.tracker.update([], pts_ms=160.0)
    # one continuous track despite the gap
    assert len([t for t in tracks]) <= 1
    assert pipeline.stats.discontinuities == 0
