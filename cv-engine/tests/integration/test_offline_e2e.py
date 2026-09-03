"""Offline end-to-end: real YOLO11 tracking + real OCR + real event pipeline.

Needs no network and no live Sentinel feed — it replays a controlled fixture
frame. It proves the chain ``frame -> detection -> tracking -> ANPR -> event``
on genuine model outputs, and that repeated frames collapse into one sighting.

The *live* Sentinel variant is ``test_live_sentinel.py`` (skipped unless
``TRINETRA_LIVE=1``). This one is intentionally part of the default suite so CI
exercises the real AI path.
"""

from __future__ import annotations

from pathlib import Path

import cv2

from capture.frames import FramePacket
from capture.sentinel_catalogue import Camera
from config.settings import load_settings
from integration.backend_client import BackendClient
from pipeline import CameraPipeline
from tracking.vehicle_tracker import VehicleTracker

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "traffic_cam04.jpg"
EXPECTED_PLATE = "GJ01AB1234"


class RecordingSession:
    def __init__(self):
        self.posted = []

    def post(self, url, json=None, timeout=None):
        self.posted.append(json)

        class R:
            status_code = 200

        return R()


def test_real_detection_tracking_anpr_produces_one_sighting(tmp_path):
    frame = cv2.imread(str(FIXTURE))
    assert frame is not None, "fixture image missing - run scripts/fetch_fixtures.sh"

    settings = load_settings(
        env={},
        anpr_interval_s=0.0,
        frame_skip=0,
        inference_interval_s=0.0,
        evidence_dir=str(tmp_path / "ev"),
        dead_letter_path=str(tmp_path / "dl.jsonl"),
        ocr_engine="rapidocr",
    )
    camera = Camera(camera_id="cam04", latitude=23.0126, longitude=72.5647)
    session = RecordingSession()
    backend = BackendClient(settings, session=session)  # not started; just a sink
    pipeline = CameraPipeline(
        settings,
        camera,
        tracker=VehicleTracker(settings),
        ocr_engine=None,
        backend=backend,
    )

    # CameraPipeline needs an OCR engine; wire the real one.
    from anpr.ocr import get_ocr_engine
    from anpr.plate_detector import PlateDetector

    pipeline.ocr = get_ocr_engine(settings)
    pipeline.plate_detector = PlateDetector(settings, pipeline.ocr)

    events = []
    for seq in range(6):
        packet = FramePacket(
            frame=frame,
            camera_id="cam04",
            pts_ms=seq * 500.0,
            continuous_ms=seq * 500.0,
            seq=seq + 1,
            source="file",
        )
        events += [e for e in pipeline.process_packet(packet) if e is not None]

    # Exactly one sighting for the plated vehicle, not one per frame.
    plated = [e for e in events if e.plate]
    assert len(plated) >= 1, "expected at least one ANPR sighting"
    assert all(e.plate == EXPECTED_PLATE for e in plated)
    assert len({e.track_id for e in plated}) == 1

    event = plated[0]
    assert event.camera_id == "cam04"
    assert event.vehicle_class == "car"
    assert event.plate_confidence > settings.anpr_conf_threshold
    assert event.latitude == 23.0126 and event.longitude == 72.5647
    assert event.evidence_ref is not None
    payload = event.to_payload()
    from events.event_schema import validate_payload

    assert validate_payload(payload) == []
    # The sighting was queued exactly once for the backend.
    assert backend.pending == 1
