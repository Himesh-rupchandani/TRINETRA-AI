#!/usr/bin/env python3
"""DEMO MODE — runs the real AI pipeline on a controlled fixture, offline.

This is clearly DEMO MODE: it uses a stored frame, not a live government feed.
The live demo is `scripts/run_pipeline.py` against the real Sentinel catalogue.

Usage: python scripts/run_demo.py

It demonstrates the exact target flow from the integration spec:
frame -> detection -> track -> ANPR -> event -> (backend queue).
"""

from __future__ import annotations

import json
from pathlib import Path

import _bootstrap

_bootstrap.boot("WARNING")

import cv2  # noqa: E402

from anpr.ocr import get_ocr_engine  # noqa: E402
from anpr.plate_detector import PlateDetector  # noqa: E402
from capture.frames import FramePacket  # noqa: E402
from capture.sentinel_catalogue import Camera  # noqa: E402
from config.settings import load_settings  # noqa: E402
from integration.backend_client import BackendClient  # noqa: E402
from pipeline import CameraPipeline  # noqa: E402
from tracking.vehicle_tracker import VehicleTracker  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "traffic_cam04.jpg"


class EchoSession:
    def __init__(self):
        self.posted = []

    def post(self, url, json=None, timeout=None):
        self.posted.append(json)

        class R:
            status_code = 200

        return R()


def main() -> int:
    print("=" * 70)
    print("DEMO MODE - controlled fixture. NOT the live Sentinel feed.")
    print("=" * 70)
    frame = cv2.imread(str(FIXTURE))
    if frame is None:
        print("ERROR: fixture missing - the demo needs tests/fixtures/traffic_cam04.jpg")
        return 1

    settings = load_settings(
        env={}, anpr_interval_s=0.0, ocr_engine="rapidocr",
        evidence_dir="./cv-engine/var/demo_evidence",
    )
    camera = Camera(camera_id="cam04", name="Paldi Circle (demo)", latitude=23.0126, longitude=72.5647)
    session = EchoSession()
    backend = BackendClient(settings, session=session)
    backend.start()
    pipeline = CameraPipeline(settings, camera, tracker=VehicleTracker(settings), backend=backend)
    pipeline.ocr = get_ocr_engine(settings)
    pipeline.plate_detector = PlateDetector(settings, pipeline.ocr)

    events = []
    for seq in range(6):
        packet = FramePacket(
            frame=frame, camera_id="cam04", pts_ms=seq * 500.0, continuous_ms=seq * 500.0,
            seq=seq + 1, source="file",
        )
        events += [e for e in pipeline.process_packet(packet) if e]

    plated = [e for e in events if e.plate]
    if not plated:
        print("No plate read on the fixture (unexpected in demo).")
        return 1
    event = plated[0]
    print("\nSentinel CAM04 -> vehicle detected -> ANPR -> event:")
    print(f"  vehicle_id(track) : {event.track_id}")
    print(f"  vehicle_class     : {event.vehicle_class}")
    print(f"  plate             : {event.plate}  (raw: {event.plate_raw})")
    print(f"  plate_confidence  : {event.plate_confidence:.2f}")
    print(f"  grade             : {event.confidence_grade}  low_confidence={event.low_confidence}")
    print(f"  location          : {event.latitude}, {event.longitude}")
    print(f"  evidence_ref      : {event.evidence_ref}")
    print("\n  event payload -> POST /api/events:")
    print("  " + json.dumps(event.to_payload(), indent=2).replace("\n", "\n  "))
    backend.stop(drain_timeout_s=3.0)
    print(f"\n  backend accepted: {backend.sent} event(s) posted (dead-lettered: {backend.dead_lettered})")
    print("\nDEMO MODE complete. For the live feed run scripts/run_pipeline.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
