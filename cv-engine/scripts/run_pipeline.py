#!/usr/bin/env python3
"""Run the real CV -> backend loop over one or more live cameras.

Usage:
  python scripts/run_pipeline.py --cameras cam04 --seconds 60
  python scripts/run_pipeline.py --auto-subset 3 --seconds 120

Start with ONE camera. The backend (BACKEND_BASE_URL) must be up; events are
queued and posted with bounded retry, failures go to the dead-letter file.
"""

from __future__ import annotations

import argparse
import time

import _bootstrap

_bootstrap.boot()

from capture.sentinel_catalogue import get_cameras, select_test_subset  # noqa: E402
from config.settings import load_settings  # noqa: E402
from integration.backend_client import BackendClient  # noqa: E402
from pipeline import run_camera  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the live CV pipeline")
    parser.add_argument("--cameras", default="", help="comma-separated camera ids")
    parser.add_argument("--auto-subset", type=int, default=0, help="pick a representative subset of N")
    parser.add_argument("--seconds", type=float, default=60.0)
    args = parser.parse_args()

    settings = load_settings()
    settings.max_cameras = max(1, len([c for c in args.cameras.split(",") if c]) or args.auto_subset or 1)
    cameras = get_cameras(settings=settings)
    if not cameras:
        print("ERROR: catalogue unavailable - cannot start a live run.")
        return 1

    if args.cameras:
        wanted = {c.strip().lower() for c in args.cameras.split(",") if c.strip()}
        cameras = [c for c in cameras if c.camera_id in wanted]
    elif args.auto_subset:
        cameras = select_test_subset(cameras, size=args.auto_subset)
    cameras = cameras[: settings.max_cameras]

    backend = BackendClient(settings)
    backend.start()
    summaries = []
    for camera in cameras:
        print(f"\n=== running {camera.camera_id} for {args.seconds}s ===")
        summary = run_camera(
            camera,
            settings,
            backend=backend,
            max_reconnects=4,
            stop_flag=lambda deadline=time.monotonic() + args.seconds: time.monotonic() > deadline,
        )
        summaries.append(summary)
    backend.stop()

    print("\n=== summaries ===")
    for s in summaries:
        for k, v in s.items():
            print(f"{k:22}: {v}")
        print("-" * 40)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
