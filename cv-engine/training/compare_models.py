#!/usr/bin/env python3
"""Side-by-side original vs fine-tuned detector on the same video frames.

    python training/compare_models.py \\
        --original models/original/yolo11s.pt \\
        --trained  models/trained/vehicles/best.pt \\
        --video    feeds/reference_traffic.mp4

Reports boxes-per-frame, class histogram, and small-box recall proxy
(boxes whose area is < 0.5% of the frame). Does not invent plates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from common import ORIGINAL_VEHICLE, REFERENCE_VIDEO, REPORTS, TRAINED_VEHICLE, ensure_dirs


def _run(weights: str, frames: list, imgsz: int, conf: float, iou: float, device: str) -> dict:
    from detection.vehicle_detector import VehicleDetector

    det = VehicleDetector(
        model_path=weights,
        conf_threshold=conf,
        imgsz=imgsz,
        device=device,
        iou_threshold=iou,
        prefer_trained=False,
    )
    n = 0
    boxes = 0
    small = 0
    classes: dict = {}
    for frame in frames:
        h, w = frame.shape[:2]
        area = float(w * h)
        ds = det.detect(frame)
        n += 1
        boxes += len(ds)
        for d in ds:
            classes[d.class_name] = classes.get(d.class_name, 0) + 1
            x1, y1, x2, y2 = d.bbox
            if (x2 - x1) * (y2 - y1) < 0.005 * area:
                small += 1
    return {
        "weights": weights,
        "frames": n,
        "boxes": boxes,
        "boxes_per_frame": round(boxes / max(n, 1), 3),
        "small_boxes": small,
        "small_boxes_per_frame": round(small / max(n, 1), 3),
        "class_histogram": classes,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--original", default=str(ORIGINAL_VEHICLE if ORIGINAL_VEHICLE.is_file() else "yolo11s.pt"))
    ap.add_argument("--trained", default=str(TRAINED_VEHICLE))
    ap.add_argument("--video", type=Path, default=REFERENCE_VIDEO)
    ap.add_argument("--samples", type=int, default=40)
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--conf", type=float, default=0.30)
    ap.add_argument("--iou", type=float, default=0.50)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()
    ensure_dirs()
    if not args.video.is_file():
        raise SystemExit(f"video not found: {args.video}")
    if not Path(args.trained).is_file():
        raise SystemExit(f"trained weights not found: {args.trained}")

    cap = cv2.VideoCapture(str(args.video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    idxs = [int(i * max(total - 1, 1) / max(args.samples - 1, 1)) for i in range(args.samples)] if total else []
    frames = []
    if idxs:
        for i in idxs:
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, fr = cap.read()
            if ok and fr is not None:
                frames.append(fr)
    else:
        while len(frames) < args.samples:
            ok, fr = cap.read()
            if not ok:
                break
            frames.append(fr)
    cap.release()
    if not frames:
        raise SystemExit("no frames decoded")

    original = _run(args.original, frames, args.imgsz, args.conf, args.iou, args.device)
    trained = _run(args.trained, frames, args.imgsz, args.conf, args.iou, args.device)
    report = {
        "video": str(args.video),
        "samples": len(frames),
        "imgsz": args.imgsz,
        "conf": args.conf,
        "original": original,
        "trained": trained,
        "delta_boxes_per_frame": round(trained["boxes_per_frame"] - original["boxes_per_frame"], 3),
        "delta_small_boxes_per_frame": round(
            trained["small_boxes_per_frame"] - original["small_boxes_per_frame"], 3
        ),
    }
    dest = REPORTS / "compare_models.json"
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"[ok] {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
