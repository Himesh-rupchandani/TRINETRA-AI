#!/usr/bin/env python3
"""
Build a MULTI-VISIT validation fixture from REAL footage.

Why this exists
---------------
The distinct-sighting logic ("the same vehicle appears N times → N sightings,
not N×200 frames") can only be validated end-to-end on a clip where a vehicle
genuinely leaves the scene and comes back. This script assembles such a clip by
re-arranging REAL recorded footage:

    [visit segment] [gap segment] [visit segment] [gap segment] ...

Nothing is rendered or simulated — every frame is real video. The result is a
*test fixture* for the pipeline's segmentation stage; it is never presented as
a real-world recording of a real journey.

    python scripts/make_multivisit_fixture.py \
        --visit samples/anpr_video1.mp4:0:5.5 \
        --gap   samples/traffic_ipcam.mp4:2:5 \
        --visits 5 --out samples/multivisit_fixture.mp4
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2


def parse_segment(spec: str):
    path, start, dur = spec.rsplit(":", 2)
    return Path(path), float(start), float(dur)


def copy_segment(writer, path: Path, start_sec: float, duration_sec: float, size, fps: float) -> int:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise IOError(f"cannot open {path}")
    cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000.0)
    written = 0
    end_ms = (start_sec + duration_sec) * 1000.0
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        if cap.get(cv2.CAP_PROP_POS_MSEC) > end_ms:
            break
        if (frame.shape[1], frame.shape[0]) != size:
            frame = cv2.resize(frame, size)
        writer.write(frame)
        written += 1
    cap.release()
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--visit", required=True, help="path:start_sec:duration_sec (vehicle present)")
    ap.add_argument("--gap", required=True, help="path:start_sec:duration_sec (vehicle absent)")
    ap.add_argument("--visits", type=int, default=5)
    ap.add_argument("--fps", type=float, default=25.0)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    v_path, v_start, v_dur = parse_segment(args.visit)
    g_path, g_start, g_dur = parse_segment(args.gap)

    probe = cv2.VideoCapture(str(v_path))
    size = (int(probe.get(cv2.CAP_PROP_FRAME_WIDTH)), int(probe.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    probe.release()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(args.out), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, size)
    if not writer.isOpened():
        raise IOError(f"cannot write {args.out}")

    total = 0
    for i in range(args.visits):
        n = copy_segment(writer, v_path, v_start, v_dur, size, args.fps)
        print(f"visit {i + 1}: {n} frames @ t={total / args.fps:.1f}s")
        total += n
        if i < args.visits - 1:
            n = copy_segment(writer, g_path, g_start, g_dur, size, args.fps)
            print(f"  gap  : {n} frames")
            total += n
    writer.release()
    print(f"wrote {args.out} ({total} frames, {total / args.fps:.1f}s, {size[0]}x{size[1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
