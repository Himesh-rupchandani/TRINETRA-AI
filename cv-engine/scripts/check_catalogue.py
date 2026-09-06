#!/usr/bin/env python3
"""Probe the Sentinel catalogue and suggest a diverse test subset (spec §27)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from capture.sentinel_catalogue import SentinelCatalogue, redact_text, redact_url, select_test_subset
from config.settings import Settings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--subset", type=int, default=4)
    args = ap.parse_args()

    settings = Settings.from_env()
    cat = SentinelCatalogue(
        url=args.url or settings.sentinel_catalogue_url,
        timeout_sec=settings.catalogue_timeout_sec,
    )
    try:
        cameras = cat.fetch()
    except Exception as exc:
        print(f"CATALOGUE UNREACHABLE: {redact_text(exc)}")
        sys.exit(1)

    print(f"Catalogue OK: {len(cameras)} cameras from {redact_url(cat.url)}\n")
    print(f"{'ID':<10} {'STATUS':<9} {'CODEC':<6} {'RES':<11} {'LOC':<28} RTSP/HLS")
    for cam in cameras:
        res = f"{cam.width}x{cam.height}" if cam.width else "?"
        loc = (cam.location or cam.name or "")[:26]
        print(
            f"{cam.camera_id:<10} {cam.status:<9} {cam.codec or '?':<6} {res:<11} {loc:<28} "
            f"{'RTSP' if cam.rtsp_url else '-'}{'/HLS' if cam.hls_url else ''}"
        )

    subset = select_test_subset(cameras, args.subset)
    print(f"\nSuggested test subset ({len(subset)} cameras, codec/resolution/status-diverse):")
    for cam in subset:
        print(f"  - {cam.camera_id}: {cam.codec} {cam.width}x{cam.height} status={cam.status}")


if __name__ == "__main__":
    main()
