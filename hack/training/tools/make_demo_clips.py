#!/usr/bin/env python3
"""
Build SYNTHETIC multi-camera test clips for the multi-video analysis feature.

WHY THIS EXISTS
---------------
Verifying "the same number plate seen in video A and in video C" needs footage
where a plate is actually legible. Public CCTV sample clips are 768x432, so
their plates are ~18 px tall and unreadable by any OCR engine. Rather than
inventing plate strings in the database (never acceptable), this script builds
an explicitly synthetic fixture: real traffic frames, real vehicle detections,
with a rendered number plate composited onto the detected vehicle.

Everything it produces is labelled SYNTHETIC. It is a test fixture for the
pipeline, NOT evidence and NOT a demo of real-world accuracy. Real accuracy
numbers can only come from the operator's own footage.

Usage
-----
    python training/tools/make_demo_clips.py \
        --source /path/to/traffic.mp4 --out-dir /tmp/demo_clips \
        --clip CAM1:GJ01AB1234 --clip CAM2:MH12XY4567 --clip CAM3:GJ01AB1234
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Tuple

import cv2
import numpy as np

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_WEIGHTS = os.path.join(REPO_ROOT, "TRINETRAAI", "backend", "models", "yolo11s.pt")
VEHICLE_CLASS_IDS = {2, 3, 5, 7}


def render_plate(text: str, width: int, height: int) -> np.ndarray:
    """Render an Indian-style white plate with black characters."""
    plate = np.full((height, width, 3), 235, dtype=np.uint8)
    cv2.rectangle(plate, (0, 0), (width - 1, height - 1), (30, 30, 30), max(1, height // 18))
    scale = 1.0
    thickness = max(1, int(round(height / 12)))
    font = cv2.FONT_HERSHEY_SIMPLEX
    # fit the text to the plate
    for _ in range(40):
        (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
        if tw > width * 0.88 or th > height * 0.62:
            scale -= 0.03
            if scale <= 0.1:
                break
        else:
            scale += 0.03
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    cv2.putText(
        plate,
        text,
        ((width - tw) // 2, (height + th) // 2),
        font,
        scale,
        (20, 20, 20),
        thickness,
        cv2.LINE_AA,
    )
    return plate


def paste_plate(frame: np.ndarray, box: Tuple[int, int, int, int], text: str) -> bool:
    """Composite a rendered plate onto the lower-centre of a vehicle box."""
    x1, y1, x2, y2 = box
    vw, vh = x2 - x1, y2 - y1
    if vw < 90 or vh < 60:
        return False
    pw = int(vw * 0.34)
    ph = max(10, int(pw * 0.24))
    px = x1 + (vw - pw) // 2
    py = y1 + int(vh * 0.74)
    if py + ph >= frame.shape[0] or px < 0 or px + pw >= frame.shape[1]:
        return False
    plate = render_plate(text, pw, ph)
    # soften so it blends with the frame's own sharpness/noise
    plate = cv2.GaussianBlur(plate, (3, 3), 0)
    roi = frame[py : py + ph, px : px + pw]
    frame[py : py + ph, px : px + pw] = cv2.addWeighted(plate, 0.94, roi, 0.06, 0)
    return True


def load_detector(weights: str):
    from ultralytics import YOLO

    return YOLO(weights)


def best_vehicle(model, frame: np.ndarray, imgsz: int, conf: float) -> Optional[Tuple[int, int, int, int]]:
    res = model.predict(frame, verbose=False, imgsz=imgsz, conf=conf, device="cpu")
    if not res or res[0].boxes is None or len(res[0].boxes) == 0:
        return None
    boxes = res[0].boxes
    best, best_area = None, 0
    for xyxy, cls in zip(boxes.xyxy.cpu().numpy(), boxes.cls.cpu().numpy()):
        if int(cls) not in VEHICLE_CLASS_IDS:
            continue
        x1, y1, x2, y2 = (int(v) for v in xyxy[:4])
        area = (x2 - x1) * (y2 - y1)
        if area > best_area:
            best, best_area = (x1, y1, x2, y2), area
    return best


def build_clip(
    source: str,
    out_path: str,
    plate_text: str,
    start_frame: int,
    n_frames: int,
    model,
    imgsz: int,
    conf: float,
) -> dict:
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    # upscale so a composited plate has a realistic-but-readable pixel height
    out_w, out_h = w * 2, h * 2
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (out_w, out_h))
    written = stamped = 0
    while written < n_frames:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_CUBIC)
        box = best_vehicle(model, frame, imgsz, conf)
        if box and paste_plate(frame, box, plate_text):
            stamped += 1
        writer.write(frame)
        written += 1
    writer.release()
    cap.release()
    return {"file": out_path, "frames": written, "frames_with_plate": stamped, "plate": plate_text}


def pick_windows(
    source: str, model, imgsz: int, conf: float, per: int, count: int, sample_every: int = 5
) -> List[int]:
    """
    Scan the source once and choose the start frames whose windows contain the
    largest vehicles — a composited plate is only useful where a vehicle is
    actually big enough to carry one.
    """
    cap = cv2.VideoCapture(source)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    scores: List[Tuple[int, int]] = []  # (frame_index, best vehicle width in source px)
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % sample_every == 0:
            box = best_vehicle(model, frame, imgsz, conf)
            scores.append((idx, (box[2] - box[0]) if box else 0))
        idx += 1
    cap.release()
    if not scores:
        return [0] * count

    # window score = sum of vehicle widths of its samples
    per_samples = max(1, per // sample_every)
    windows: List[Tuple[int, int]] = []
    for s in range(0, max(1, len(scores) - per_samples), max(1, per_samples // 2)):
        chunk = scores[s : s + per_samples]
        windows.append((chunk[0][0], sum(w for _, w in chunk)))
    windows.sort(key=lambda t: -t[1])

    chosen: List[int] = []
    for start, _score in windows:
        if all(abs(start - c) >= per // 2 for c in chosen):
            chosen.append(start)
        if len(chosen) == count:
            break
    while len(chosen) < count:  # short source: reuse the best window
        chosen.append(windows[0][0] if windows else 0)
    chosen = [min(c, max(0, total - per - 1)) for c in chosen]
    print(f"[synthetic] selected start frames {chosen} (of {total})")
    return chosen


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--clip", action="append", required=True, help="NAME:PLATE (repeatable)")
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--weights", default=DEFAULT_WEIGHTS)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--conf", type=float, default=0.35)
    args = ap.parse_args(argv)

    os.makedirs(args.out_dir, exist_ok=True)
    cap = cv2.VideoCapture(args.source)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    per = int(args.seconds * fps)
    model = load_detector(args.weights)

    specs = []
    for i, spec in enumerate(args.clip):
        name, _, plate = spec.partition(":")
        specs.append((name.strip() or f"CAM{i + 1}", plate.strip().upper()))

    starts = pick_windows(args.source, model, args.imgsz, args.conf, per, len(specs))
    for i, (name, plate) in enumerate(specs):
        start = starts[i]
        out = os.path.join(args.out_dir, f"{name}.mp4")
        info = build_clip(args.source, out, plate, start, per, model, args.imgsz, args.conf)
        print(
            f"[synthetic] {name}: {info['frames']} frames, "
            f"plate '{plate}' composited on {info['frames_with_plate']} of them -> {out}"
        )
    print("\nNOTE: these clips are SYNTHETIC test fixtures (rendered plates on real frames).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
