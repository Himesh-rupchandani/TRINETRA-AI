#!/usr/bin/env python3
"""Download the reference Gujarat traffic video from Google Drive.

    python training/download_reference.py
    python training/download_reference.py --out feeds/reference_traffic.mp4

The Drive file is VID20260907113848.mp4 (184 MB). This sandbox often cannot
complete a TLS handshake to drive.google.com; on a normal machine `gdown`
works. Place the file at cv-engine/feeds/reference_traffic.mp4 if you already
have it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import FEEDS_DIR, REFERENCE_DRIVE_ID, REFERENCE_VIDEO, ensure_dirs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=REFERENCE_VIDEO)
    ap.add_argument("--id", default=REFERENCE_DRIVE_ID)
    args = ap.parse_args()
    ensure_dirs()
    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.is_file() and out.stat().st_size > 1024 * 1024:
        print(f"[ok] already present: {out} ({out.stat().st_size / 1e6:.1f} MB)")
        return 0
    try:
        import gdown
    except ImportError:
        print("gdown is not installed. pip install gdown", file=sys.stderr)
        print(
            f"Or download https://drive.google.com/file/d/{args.id}/view "
            f"manually to {out}",
            file=sys.stderr,
        )
        return 1
    url = f"https://drive.google.com/uc?id={args.id}"
    print(f"[download] {url} -> {out}")
    try:
        gdown.download(url, str(out), quiet=False)
    except Exception as exc:
        print(f"[fail] Google Drive download blocked or failed: {exc}", file=sys.stderr)
        print(f"Place {REFERENCE_VIDEO.name} manually at {out}", file=sys.stderr)
        return 1
    if not out.is_file() or out.stat().st_size < 1024 * 1024:
        print("[fail] downloaded file missing or too small", file=sys.stderr)
        return 1
    print(f"[ok] {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
