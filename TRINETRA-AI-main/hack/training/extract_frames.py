#!/usr/bin/env python3
"""
PART 4a — extract representative training frames from real footage.

Two rules make this dataset honest:

1. **Representative, not consecutive.** Consecutive CCTV frames are almost
   identical; a dataset full of them teaches the model one moment, not one
   road. Frames are sampled at a stride and then filtered by an inter-frame
   difference so near-duplicates are dropped.
2. **No leakage between splits.** The video is cut into contiguous TIME
   SEGMENTS and whole segments are assigned to train / val / test. A vehicle
   that drives through the scene therefore appears in exactly one split, which
   a random per-frame split would never guarantee.

Output layout (ready for build_dataset.py):

    <out>/images/train/<stem>_000123.jpg
    <out>/images/val/...
    <out>/images/test/...
    <out>/manifest.json      frame -> source video, frame index, time, segment

Usage:
    python training/extract_frames.py --video footage/junction.mp4 \
        --out training/dataset --max-frames 400
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List

import cv2
import numpy as np

SPLITS = ("train", "val", "test")


def _difference(a: np.ndarray, b: np.ndarray) -> float:
    """Mean absolute difference of two small greyscale thumbnails (0..1)."""
    ga = cv2.cvtColor(cv2.resize(a, (96, 54)), cv2.COLOR_BGR2GRAY).astype(np.float32)
    gb = cv2.cvtColor(cv2.resize(b, (96, 54)), cv2.COLOR_BGR2GRAY).astype(np.float32)
    return float(np.abs(ga - gb).mean() / 255.0)


def segment_of(frame_idx: int, total: int, segments: int) -> int:
    if total <= 0:
        return 0
    return min(segments - 1, int(frame_idx / total * segments))


def split_for_segment(seg: int, segments: int, ratios=(0.7, 0.15, 0.15)) -> str:
    """
    Contiguous time segments -> splits. The FIRST segments train, the middle
    validate, the LAST test: evaluation then happens on footage the model has
    never seen a single frame near.
    """
    n_train = max(1, int(round(segments * ratios[0])))
    n_val = max(1, int(round(segments * ratios[1])))
    if seg < n_train:
        return "train"
    if seg < n_train + n_val:
        return "val"
    return "test"


def extract(
    video: Path,
    out: Path,
    stride: int,
    max_frames: int,
    segments: int,
    min_diff: float,
    resize_to: int,
) -> dict:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"Cannot open video: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    stem = video.stem.replace(" ", "_")

    for s in SPLITS:
        (out / "images" / s).mkdir(parents=True, exist_ok=True)
        (out / "labels" / s).mkdir(parents=True, exist_ok=True)

    manifest: List[dict] = []
    kept_per_split = {s: 0 for s in SPLITS}
    last_kept: dict = {}
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        if idx % stride == 0 and sum(kept_per_split.values()) < max_frames:
            seg = segment_of(idx, total, segments)
            split = split_for_segment(seg, segments)
            prev = last_kept.get(split)
            if prev is None or _difference(prev, frame) >= min_diff:
                img = frame
                if resize_to and max(frame.shape[:2]) > resize_to:
                    scale = resize_to / max(frame.shape[:2])
                    img = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                name = f"{stem}_{idx:06d}.jpg"
                cv2.imwrite(str(out / "images" / split / name), img,
                            [int(cv2.IMWRITE_JPEG_QUALITY), 92])
                manifest.append({
                    "file": f"images/{split}/{name}",
                    "source_video": str(video),
                    "frame_index": idx,
                    "time_sec": round(idx / fps, 3),
                    "segment": seg,
                    "split": split,
                    "width": img.shape[1],
                    "height": img.shape[0],
                })
                last_kept[split] = frame
                kept_per_split[split] += 1
        idx += 1
    cap.release()

    manifest_path = out / "manifest.json"
    existing = []
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            existing = []
    keep = [m for m in existing if m.get("source_video") != str(video)]
    manifest_path.write_text(json.dumps(keep + manifest, indent=2))

    return {
        "video": str(video),
        "frames_in_video": total,
        "fps": fps,
        "extracted": kept_per_split,
        "manifest": str(manifest_path),
    }


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", required=True, action="append",
                    help="Source video (repeat for several)")
    ap.add_argument("--out", default="training/dataset")
    ap.add_argument("--stride", type=int, default=10, help="sample every Nth frame")
    ap.add_argument("--max-frames", type=int, default=400, help="per video")
    ap.add_argument("--segments", type=int, default=10, help="time segments per video")
    ap.add_argument("--min-diff", type=float, default=0.02,
                    help="0..1 minimum visual change vs the last kept frame")
    ap.add_argument("--resize-to", type=int, default=1280, help="0 = keep original size")
    args = ap.parse_args(argv)

    out = Path(args.out)
    for v in args.video:
        info = extract(Path(v), out, args.stride, args.max_frames,
                       args.segments, args.min_diff, args.resize_to)
        print(f"[extract] {os.path.basename(v)}: {info['extracted']} "
              f"(of {info['frames_in_video']} frames)")
    print(f"[extract] manifest -> {out / 'manifest.json'}")
    print("[extract] splits are whole TIME SEGMENTS — no frame leaks between them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
