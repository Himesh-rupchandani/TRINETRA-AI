#!/usr/bin/env python3
"""Sample diverse frames from a traffic video. Does NOT dump every frame.

    python training/extract_frames.py --video feeds/reference_traffic.mp4

Strategy:
  1. Walk the video at a target interval (default 1.0 s).
  2. Drop near-duplicates via 32×18 grayscale correlation.
  3. Keep the first/last frame of each stretch so scene changes survive.
  4. Write JPEGs under training/datasets/vehicles/images/raw/ (unsorted).
  5. Split by TIME (not random) into train/val/test to avoid leakage.

A 184 MB ~2–4 min clip yields roughly 80–180 frames, which is the right
size to fine-tune YOLO11s with heavy augmentation — not to train from scratch.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from common import FRAMES_DIR, REFERENCE_VIDEO, REPORTS, VEHICLE_DS, ensure_dirs


def signature(frame: np.ndarray) -> np.ndarray:
    small = cv2.resize(frame, (32, 18), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    return gray.ravel()


def is_duplicate(sig: np.ndarray, prev: list, thresh: float = 0.985) -> bool:
    if not prev:
        return False
    # Compare against the last few kept signatures only (local duplicates).
    for p in prev[-8:]:
        num = float(np.dot(sig, p))
        den = float(np.linalg.norm(sig) * np.linalg.norm(p) + 1e-9)
        if num / den >= thresh:
            return True
    return False


def extract(
    video: Path,
    interval_sec: float = 1.0,
    max_frames: int = 200,
    corr_thresh: float = 0.985,
) -> list:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"cannot open {video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    if fps <= 1e-3:
        fps = 25.0
    step = max(1, int(round(fps * interval_sec)))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    raw_dir = VEHICLE_DS / "images" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    kept = []
    prev_sigs = []
    idx = 0
    saved = 0
    while saved < max_frames:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        if idx % step != 0:
            idx += 1
            continue
        sig = signature(frame)
        if is_duplicate(sig, prev_sigs, corr_thresh):
            idx += 1
            continue
        name = f"{video.stem}_{idx:06d}.jpg"
        dest = raw_dir / name
        cv2.imwrite(str(dest), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        t_sec = idx / fps
        kept.append({"file": name, "frame_index": idx, "t_sec": round(t_sec, 3), "path": str(dest)})
        prev_sigs.append(sig)
        saved += 1
        idx += 1
    cap.release()
    return kept, fps, total


def split_by_time(kept: list, train=0.70, val=0.15) -> dict:
    """Split by timeline position. Adjacent frames never cross the cut."""
    if not kept:
        return {"train": [], "val": [], "test": []}
    times = [k["t_sec"] for k in kept]
    t0, t1 = min(times), max(times)
    span = max(t1 - t0, 1e-6)
    buckets = {"train": [], "val": [], "test": []}
    for k in kept:
        frac = (k["t_sec"] - t0) / span
        if frac < train:
            buckets["train"].append(k)
        elif frac < train + val:
            buckets["val"].append(k)
        else:
            buckets["test"].append(k)
    # Guarantee each split has at least one image when we have ≥ 3 frames.
    if len(kept) >= 3:
        for split, fallback in (("val", "train"), ("test", "train")):
            if not buckets[split] and buckets[fallback]:
                buckets[split].append(buckets[fallback].pop())
    return buckets


def copy_into_splits(buckets: dict) -> None:
    for split, items in buckets.items():
        img_dir = VEHICLE_DS / "images" / split
        img_dir.mkdir(parents=True, exist_ok=True)
        for item in items:
            src = Path(item["path"])
            dest = img_dir / src.name
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
            item["split"] = split
            item["split_path"] = str(dest)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", type=Path, default=REFERENCE_VIDEO)
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between candidate frames")
    ap.add_argument("--max-frames", type=int, default=200)
    ap.add_argument("--corr", type=float, default=0.985, help="duplicate correlation threshold")
    args = ap.parse_args()
    ensure_dirs()
    if not args.video.is_file():
        raise SystemExit(
            f"video not found: {args.video}\n"
            "Run: python training/download_reference.py\n"
            "or copy VID20260907113848.mp4 to cv-engine/feeds/reference_traffic.mp4"
        )
    print(f"[extract] {args.video} every {args.interval}s (max {args.max_frames})")
    kept, fps, total = extract(args.video, args.interval, args.max_frames, args.corr)
    buckets = split_by_time(kept)
    copy_into_splits(buckets)
    summary = {
        "video": str(args.video),
        "fps": fps,
        "frame_count": total,
        "kept": len(kept),
        "train": len(buckets["train"]),
        "val": len(buckets["val"]),
        "test": len(buckets["test"]),
        "interval_sec": args.interval,
        "items": kept,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "extracted_frames.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        f"[ok] kept {len(kept)} frames  "
        f"train={len(buckets['train'])} val={len(buckets['val'])} test={len(buckets['test'])}"
    )
    print(f"     {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
