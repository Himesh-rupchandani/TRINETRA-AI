#!/usr/bin/env python3
"""Probe one camera and report *measured* stream behaviour.

Usage: python scripts/probe_camera.py cam04 [--seconds 15]

Reports delivered FPS (from PTS), codec, resolution, decode latency and whether
the feed loops. If a camera cannot be opened from this network the script says
so plainly rather than inventing numbers.
"""

from __future__ import annotations

import argparse
import time

import _bootstrap

_bootstrap.boot("WARNING")

from capture.capture_factory import open_capture  # noqa: E402
from capture.sentinel_catalogue import require_camera  # noqa: E402
from config.settings import load_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe one Sentinel camera")
    parser.add_argument("camera", help="camera id from the catalogue, e.g. cam04")
    parser.add_argument("--seconds", type=float, default=15.0)
    args = parser.parse_args()

    settings = load_settings()
    try:
        camera = require_camera(args.camera, settings=settings)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: catalogue unavailable or camera unknown: {exc}")
        return 1

    capture, error = open_capture(camera, settings)
    if capture is None:
        print(f"ERROR: could not open {camera.camera_id}: {error}")
        return 1

    print(f"# probing {camera.camera_id} via {capture.source} for {args.seconds}s")
    deadline = time.monotonic() + args.seconds
    frames = 0
    try:
        while time.monotonic() < deadline:
            packet = capture.read()
            if packet is None:
                time.sleep(0.05)
                continue
            frames += 1
    finally:
        capture.close()

    stats = capture.stats
    print(f"camera            : {camera.camera_id}")
    print(f"transport         : {capture.source}")
    print(f"codec             : {stats.codec or capture.stats.extras.get('backend_fourcc') or '-'}")
    print(f"resolution        : {stats.width}x{stats.height}")
    print(f"frames decoded    : {frames}")
    print(f"delivered_fps     : {stats.delivered_fps}")
    print(f"reported_fps      : {stats.extras.get('reported_fps_untrusted')} (untrusted)")
    print(f"avg_decode_ms     : {round(stats.avg_decode_ms, 2)}")
    print(f"decode_failures   : {stats.decode_failures}")
    print(f"loops_detected    : {stats.loops_detected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
