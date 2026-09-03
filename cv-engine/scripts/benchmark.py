#!/usr/bin/env python3
"""Benchmark real stage latencies on the fixture (no network).

Measures detection, tracking and ANPR latency plus a resource snapshot, so the
"performance measured" checkbox comes from actual timers, not guesses.

Usage: python scripts/benchmark.py [--iterations 20]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import _bootstrap

_bootstrap.boot("WARNING")

import cv2  # noqa: E402

from anpr.ocr import get_ocr_engine  # noqa: E402
from config.settings import load_settings  # noqa: E402
from detection.vehicle_detector import VehicleDetector  # noqa: E402
from metrics import MetricsCollector  # noqa: E402
from tracking.vehicle_tracker import VehicleTracker  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "traffic_cam04.jpg"


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark CV stage latencies")
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()

    frame = cv2.imread(str(FIXTURE))
    if frame is None:
        print("ERROR: fixture missing")
        return 1
    settings = load_settings(env={}, ocr_engine="rapidocr")
    metrics = MetricsCollector()

    detector = VehicleDetector(settings)
    detector.detect(frame, "cam04", 0.0)  # warm
    det = metrics.timer("detect")
    for _ in range(args.iterations):
        t0 = time.perf_counter()
        detector.detect(frame, "cam04", 0.0)
        det(time.perf_counter() - t0)

    tracker = VehicleTracker(settings)
    tracker.update(frame, "cam04", 0.0, 0.0)  # warm
    trk = metrics.timer("track")
    for _ in range(args.iterations):
        t0 = time.perf_counter()
        tracker.update(frame, "cam04", 0.0, 0.0)
        trk(time.perf_counter() - t0)

    # ANPR: crop the strongest vehicle and OCR it.
    tracks = tracker.update(frame, "cam04", 1.0, 1.0)
    crop = next((t.crop(frame) for t in tracks if t.crop(frame) is not None), None)
    if crop is not None:
        ocr = get_ocr_engine(settings)
        ocr.recognize(crop)  # warm
        anpr = metrics.timer("anpr")
        for _ in range(args.iterations):
            t0 = time.perf_counter()
            ocr.recognize(crop)
            anpr(time.perf_counter() - t0)

    summary = metrics.summary()
    print(json.dumps(summary, indent=2))
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
