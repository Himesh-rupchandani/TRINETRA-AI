#!/usr/bin/env python3
"""
Build SYNTHETIC demo clips from still traffic photos for the plate-search
feature — for environments that have no CCTV footage to upload.

Same philosophy as ``make_demo_clips.py``: real traffic frames + real vehicle
detections, with a rendered number plate composited onto the detected vehicle
and a slow Ken-Burns zoom so the tracker sees a continuous vehicle pass.
Everything produced is explicitly a SYNTHETIC fixture for exercising the
pipeline end-to-end, never evidence.

Usage
-----
    python training/tools/make_image_demo_clips.py --out-dir /tmp/demo_clips \
        --clip trinetra_detection/sample_data/sample_1.jpg:CAM1:GJ01AB1234 \
        --clip trinetra_detection/sample_data/sample_2.jpg:CAM2:MH12XY4567
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Tuple

import cv2

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "training", "tools"))

from make_demo_clips import best_vehicle, load_detector, paste_plate  # noqa: E402

DEFAULT_WEIGHTS = os.path.join(REPO_ROOT, "trinetra_detection", "models", "yolo11n.pt")
UPSCALE = 1.5


def _box_at_zoom(box: Tuple[int, int, int, int], zoom: float, w: int, h: int) -> Tuple[int, int, int, int]:
    """
    Map a frame-0 (out-space) detection box to frame i under the centred zoom.

    Base pixel p lands at out coord ``(p * zoom - x0) * UPSCALE`` where
    ``x0 = w * (zoom - 1) / 2``; frame 0 has zoom = 1 so out = p * UPSCALE.
    """
    x0, y0 = w * (zoom - 1) / 2, h * (zoom - 1) / 2
    x1, y1, x2, y2 = (v / UPSCALE for v in box)
    return (
        int((x1 * zoom - x0) * UPSCALE),
        int((y1 * zoom - y0) * UPSCALE),
        int((x2 * zoom - x0) * UPSCALE),
        int((y2 * zoom - y0) * UPSCALE),
    )


def build_clip_from_image(
    image: str,
    out_path: str,
    plate_text: str,
    model,
    frames: int = 150,
    fps: float = 25.0,
    imgsz: int = 640,
    conf: float = 0.35,
) -> dict:
    base = cv2.imread(image)
    if base is None:
        raise SystemExit(f"cannot read {image}")
    h, w = base.shape[:2]
    out_w, out_h = int(w * UPSCALE), int(h * UPSCALE)
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (out_w, out_h))

    zoom0 = cv2.resize(base, (out_w, out_h), interpolation=cv2.INTER_CUBIC)
    box0: Optional[Tuple[int, int, int, int]] = best_vehicle(model, zoom0, imgsz, conf)
    if box0 is None:
        raise SystemExit(f"no vehicle detected in {image} — pick another photo")

    stamped = 0
    for i in range(frames):
        zoom = 1.0 + 0.10 * (i / max(frames - 1, 1))  # slow push-in
        zw, zh = int(w * zoom), int(h * zoom)
        x0, y0 = (zw - w) // 2, (zh - h) // 2
        zoomed = cv2.resize(base, (zw, zh), interpolation=cv2.INTER_CUBIC)
        frame = cv2.resize(zoomed[y0:y0 + h, x0:x0 + w], (out_w, out_h),
                           interpolation=cv2.INTER_CUBIC)
        box = box0 if i == 0 else _box_at_zoom(box0, zoom, w, h)
        if paste_plate(frame, box, plate_text):
            stamped += 1
        writer.write(frame)
    writer.release()
    return {"file": out_path, "frames": frames, "stamped_frames": stamped, "plate": plate_text}


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--clip", action="append", required=True,
                    help="IMAGE:NAME:PLATE (repeatable)")
    ap.add_argument("--frames", type=int, default=150)
    ap.add_argument("--weights", default=DEFAULT_WEIGHTS)
    args = ap.parse_args(argv)

    os.makedirs(args.out_dir, exist_ok=True)
    model = load_detector(args.weights)
    for spec in args.clip:
        image, name, plate = spec.split(":", 2)
        out = os.path.join(args.out_dir, f"{name}.mp4")
        info = build_clip_from_image(image, out, plate, model, frames=args.frames)
        print(f"[synthetic-image] {info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
