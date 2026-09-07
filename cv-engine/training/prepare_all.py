#!/usr/bin/env python3
"""One-command dataset preparation for the reference traffic video.

    python training/prepare_all.py --video feeds/reference_traffic.mp4

Does:
  1. Download the Drive clip if missing (best-effort).
  2. Analyze footage (resolution / FPS / lighting / plate scale).
  3. Extract diverse frames (time-based, de-duplicated).
  4. Auto-label with stock YOLO11s + autorickshaw heuristic + plate morphology.
  5. Write data.yaml for vehicles and plates.

Does NOT train. Review the labels, then run train_vehicles.py / train_plates.py.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable


def _run(script: str, extra: list) -> int:
    cmd = [PY, str(HERE / script), *extra]
    print("\n$", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(HERE.parent))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", default="feeds/reference_traffic.mp4")
    ap.add_argument("--interval", default="1.0")
    ap.add_argument("--max-frames", default="200")
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--skip-label", action="store_true")
    ap.add_argument("--weights", default="models/original/yolo11s.pt")
    args = ap.parse_args()

    if not args.skip_download:
        rc = _run("download_reference.py", ["--out", args.video])
        if rc != 0:
            print("[warn] download failed — continuing if the file is already on disk")

    rc = _run("analyze_video.py", ["--video", args.video])
    if rc != 0:
        return rc
    rc = _run(
        "extract_frames.py",
        ["--video", args.video, "--interval", args.interval, "--max-frames", args.max_frames],
    )
    if rc != 0:
        return rc
    if not args.skip_label:
        rc = _run("auto_label.py", ["--weights", args.weights])
        if rc != 0:
            return rc
    print("\n[ok] dataset ready. Review labels, then:")
    print("  python training/train_vehicles.py --model models/original/yolo11s.pt --device 0")
    print("  python training/train_plates.py   --model yolo11n.pt --device 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
