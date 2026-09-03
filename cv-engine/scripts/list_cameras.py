#!/usr/bin/env python3
"""List the Sentinel camera grid from the catalogue.

Usage: python scripts/list_cameras.py [--ids cam04,cam08] [--json]

Camera IDs are never assumed; whatever the catalogue publishes is what you get.
"""

from __future__ import annotations

import argparse
import json

import _bootstrap

_bootstrap.boot("WARNING")

from capture.sentinel_catalogue import get_cameras, select_test_subset  # noqa: E402
from config.settings import load_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="List Sentinel cameras")
    parser.add_argument("--ids", default="", help="comma-separated ids to show")
    parser.add_argument("--suggest", type=int, default=0, help="show a representative test subset of N")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    cameras = get_cameras(settings=settings)
    if not cameras:
        print(
            "ERROR: could not load the catalogue from "
            f"{settings.sentinel_catalogue_url}. Check network/egress and the URL."
        )
        return 1

    if args.suggest:
        cameras = select_test_subset(cameras, size=args.suggest)
        print(f"# representative test subset ({args.suggest}):")

    wanted = {i.strip().lower() for i in args.ids.split(",") if i.strip()}
    shown = [c for c in cameras if not wanted or c.camera_id in wanted]

    if args.json:
        print(json.dumps([{"id": c.camera_id, **{k: v for k, v in c.__dict__.items() if k != "raw"}} for c in shown], indent=2))
        return 0

    print(f"{'id':8} {'status':8} {'codec':5} {'resolution':11} {'fps':4} {'rtsp':4} {'hls':4} location")
    for c in shown:
        res = f"{c.width}x{c.height}" if c.resolution else "-"
        print(
            f"{c.camera_id:8} {(c.status or '-'):8} {(c.codec or '-'):5} {res:11} "
            f"{c.fps if c.fps else '-':4} {'y' if c.rtsp_url else '-':4} {'y' if c.hls_url else '-':4} "
            f"{c.location or '-'}"
        )
    print(f"\n{len(shown)} of {len(get_cameras(settings=settings))} cameras shown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
