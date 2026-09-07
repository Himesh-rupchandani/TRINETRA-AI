#!/usr/bin/env python3
"""Pseudo-label extracted frames with the STOCK YOLO11s model.

    python training/auto_label.py --weights models/original/yolo11s.pt

This is a STARTING POINT for annotation, not ground truth:

* Stock COCO has no `autorickshaw` class — yellow/green three-wheelers
  that COCO called `car` are re-tagged when the colour heuristic fires.
* Plate boxes come from the morphology detector (and a plate YOLO if
  present). They MUST be reviewed before plate-model training.
* Review in any YOLO tool (Label Studio, CVAT, Roboflow, LabelImg).

High-res (imgsz 1280) inference is used for labelling so small/far
vehicles that 640-px inference would miss still get a box.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from common import (
    CV_ROOT,
    ORIGINAL_VEHICLE,
    PLATE_DS,
    REPORTS,
    TRAINED_PLATE,
    VEHICLE_CLASSES,
    VEHICLE_DS,
    ensure_dirs,
)


def _yolo_line(cls: int, box, w: int, h: int) -> str:
    x1, y1, x2, y2 = box
    cx = ((x1 + x2) / 2.0) / w
    cy = ((y1 + y2) / 2.0) / h
    bw = (x2 - x1) / w
    bh = (y2 - y1) / h
    cx, cy = min(max(cx, 0), 1), min(max(cy, 0), 1)
    bw, bh = min(max(bw, 1e-6), 1), min(max(bh, 1e-6), 1)
    return f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"


def _autorickshaw_heuristic(crop: np.ndarray) -> bool:
    """Weak colour cue: Gujarat autos are yellow/green with a boxy cabin."""
    if crop is None or crop.size == 0:
        return False
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    yellow = ((h >= 15) & (h <= 40) & (s > 80) & (v > 80)).mean()
    green = ((h >= 35) & (h <= 90) & (s > 60) & (v > 60)).mean()
    hh, ww = crop.shape[:2]
    aspect = ww / float(hh + 1e-6)
    # Autos are boxier than sedans and very yellow/green.
    return (yellow > 0.12 or green > 0.10) and 0.6 <= aspect <= 1.6


def _write_yaml(path: Path, names: list, root: Path) -> None:
    lines = [
        f"path: {root}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
    ]
    for i, n in enumerate(names):
        lines.append(f"  {i}: {n}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", type=Path, default=ORIGINAL_VEHICLE)
    ap.add_argument("--imgsz", type=int, default=1280, help="labelling resolution (higher = more small vehicles)")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--skip-plates", action="store_true")
    args = ap.parse_args()
    ensure_dirs()

    splits = ["train", "val", "test"]
    images = []
    for sp in splits:
        images.extend(sorted((VEHICLE_DS / "images" / sp).glob("*.jpg")))
        images.extend(sorted((VEHICLE_DS / "images" / sp).glob("*.png")))
    if not images:
        raise SystemExit("no extracted frames. Run training/extract_frames.py first.")

    weights = args.weights
    if not weights.is_file():
        # Fall back to whatever Ultralytics can resolve.
        weights = Path("yolo11s.pt")
        print(f"[warn] {args.weights} missing — will try {weights} (Ultralytics download)")

    from ultralytics import YOLO

    from anpr.plate_detector import morphology_plate_boxes
    from detection.classes import normalize_vehicle_class
    from detection.model_paths import resolve_plate_model_path

    model = YOLO(str(weights))
    plate_path = resolve_plate_model_path(str(TRAINED_PLATE) if TRAINED_PLATE.is_file() else "")
    plate_model = YOLO(plate_path) if plate_path and not args.skip_plates else None

    stats = {c: 0 for c in VEHICLE_CLASSES}
    stats["plates"] = 0
    n_images_with_veh = 0
    review_flags = []

    for img_path in images:
        frame = cv2.imread(str(img_path))
        if frame is None:
            continue
        h, w = frame.shape[:2]
        split = img_path.parent.name  # train/val/test
        results = model.predict(
            frame, verbose=False, conf=args.conf, imgsz=args.imgsz,
            device=args.device, classes=[2, 3, 5, 7],
        )
        veh_lines = []
        plate_lines = []
        if results and results[0].boxes is not None:
            boxes = results[0].boxes
            xyxy = boxes.xyxy.cpu().numpy()
            clss = boxes.cls.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            names = getattr(model, "names", {}) or {}
            for box, cls_id, conf in zip(xyxy, clss, confs):
                raw = names.get(int(cls_id), "car")
                name = normalize_vehicle_class(raw) or "car"
                x1, y1, x2, y2 = (int(v) for v in box)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                crop = frame[y1:y2, x1:x2]
                if name == "car" and _autorickshaw_heuristic(crop):
                    name = "autorickshaw"
                    review_flags.append({"image": img_path.name, "reason": "autorickshaw heuristic", "conf": float(conf)})
                if name not in VEHICLE_CLASSES:
                    continue
                cls = VEHICLE_CLASSES.index(name)
                veh_lines.append(_yolo_line(cls, (x1, y1, x2, y2), w, h))
                stats[name] += 1

                if args.skip_plates:
                    continue
                # Plate boxes in vehicle-crop coordinates, remapped to the frame.
                pboxes = []
                if plate_model is not None and crop.size > 0:
                    pr = plate_model.predict(crop, verbose=False, conf=0.25, imgsz=640)
                    if pr and pr[0].boxes is not None:
                        for pb in pr[0].boxes.xyxy.cpu().numpy():
                            pboxes.append(tuple(int(v) for v in pb))
                if not pboxes:
                    for pb in morphology_plate_boxes(crop):
                        pboxes.append(pb[:4])
                for px1, py1, px2, py2 in pboxes:
                    fx1, fy1, fx2, fy2 = x1 + px1, y1 + py1, x1 + px2, y1 + py2
                    if fx2 - fx1 < 12 or fy2 - fy1 < 8:
                        continue
                    plate_lines.append(_yolo_line(0, (fx1, fy1, fx2, fy2), w, h))
                    stats["plates"] += 1

        if veh_lines:
            n_images_with_veh += 1
        label_path = VEHICLE_DS / "labels" / split / (img_path.stem + ".txt")
        label_path.parent.mkdir(parents=True, exist_ok=True)
        label_path.write_text("\n".join(veh_lines) + ("\n" if veh_lines else ""), encoding="utf-8")

        # Mirror the image into the plate dataset so both tasks share splits.
        plate_img = PLATE_DS / "images" / split / img_path.name
        plate_img.parent.mkdir(parents=True, exist_ok=True)
        if not plate_img.exists():
            import shutil
            shutil.copy2(img_path, plate_img)
        plate_lbl = PLATE_DS / "labels" / split / (img_path.stem + ".txt")
        plate_lbl.parent.mkdir(parents=True, exist_ok=True)
        plate_lbl.write_text("\n".join(plate_lines) + ("\n" if plate_lines else ""), encoding="utf-8")

    _write_yaml(VEHICLE_DS / "data.yaml", VEHICLE_CLASSES, VEHICLE_DS)
    _write_yaml(PLATE_DS / "data.yaml", ["license_plate"], PLATE_DS)

    summary = {
        "images": len(images),
        "images_with_vehicles": n_images_with_veh,
        "counts": stats,
        "review_flags": review_flags[:50],
        "note": (
            "AUTO-LABELS. Review before trusting mAP. Autorickshaw tags are a "
            "colour heuristic; plate boxes are morphology/YOLO proposals. "
            "Delete a label file's line rather than invent a plate."
        ),
    }
    out = REPORTS / "auto_label_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[ok] labelled {len(images)} images  counts={stats}")
    print(f"     review flags: {len(review_flags)}  -> {out}")
    print("     NEXT: open the labels in CVAT/Label Studio and correct them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
