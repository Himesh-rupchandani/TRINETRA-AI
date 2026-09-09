#!/usr/bin/env python3
"""
Evaluate a plate detector on the synthetic val subsets (or any YOLO-format
image folder). Reports recall@IoU0.5 at conf 0.25 — overall and per plate-size
bucket — so regressions like "blind on close-ups" are impossible to miss.

Usage:
    python training/evaluate_plate_model.py --model path/to/best.pt \
        --data /tmp/anpr_synth --subsets val_main val_closeup val_tiny
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


def iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def evaluate(model: YOLO, img_dir: Path, lbl_dir: Path, conf: float = 0.25) -> dict:
    stats = {"n": 0, "hit": 0, "rel": []}
    buckets = {"tiny(<5%)": {"n": 0, "hit": 0}, "small(5-15%)": {"n": 0, "hit": 0},
               "mid(15-35%)": {"n": 0, "hit": 0}, "large(>35%)": {"n": 0, "hit": 0}}
    plate_ids = {k for k, v in (model.names or {}).items() if "plate" in str(v).lower()}
    for img_path in sorted(img_dir.glob("*.jpg")):
        lbl = lbl_dir / (img_path.stem + ".txt")
        if not lbl.exists():
            continue
        lines = [l.split() for l in lbl.read_text().strip().splitlines() if l.strip()]
        img = cv2.imread(str(img_path))
        H, W = img.shape[:2]
        gts = []
        for parts in lines:
            _, xc, yc, bw, bh = (float(p) for p in parts[:5])
            gts.append(((xc - bw / 2) * W, (yc - bh / 2) * H, (xc + bw / 2) * W, (yc + bh / 2) * H))
        stats["n"] += len(gts)
        results = model.predict(img, verbose=False, conf=conf, imgsz=512, device="cpu")
        dets = []
        r = results[0] if results else None
        if r is not None and r.boxes is not None:
            for xyxy, c, k in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(),
                                  r.boxes.cls.cpu().numpy()):
                if not plate_ids or int(k) in plate_ids:
                    dets.append((xyxy.tolist(), float(c)))
        for gt in gts:
            best = max((iou(gt, d[0]) for d in dets), default=0.0)
            hit = best >= 0.5
            stats["hit"] += int(hit)
            if best > 0:
                for d in dets:
                    if iou(gt, d[0]) == best:
                        stats["rel"].append(d[1])
            bw_frac = (gt[2] - gt[0]) / W
            key = ("tiny(<5%)" if bw_frac < 0.05 else "small(5-15%)" if bw_frac < 0.15
                   else "mid(15-35%)" if bw_frac < 0.35 else "large(>35%)")
            buckets[key]["n"] += 1
            buckets[key]["hit"] += int(hit)
    out = {"boxes": stats["n"], "recall": round(stats["hit"] / max(1, stats["n"]), 3),
           "mean_conf_of_matches": round(float(np.mean(stats["rel"])), 3) if stats["rel"] else None}
    for k, v in buckets.items():
        out[k] = f"{v['hit']}/{v['n']} ({v['hit'] / max(1, v['n']):.0%})"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--data", required=True, help="dataset root with images/ + labels/")
    ap.add_argument("--subsets", nargs="+", default=["val_main", "val_closeup", "val_tiny"])
    ap.add_argument("--conf", type=float, default=0.25)
    args = ap.parse_args()
    model = YOLO(args.model)
    print(f"== {args.model} ==")
    for subset in args.subsets:
        img_dir = Path(args.data) / "images" / subset
        lbl_dir = Path(args.data) / "labels" / subset
        if not img_dir.exists():
            continue
        r = evaluate(model, img_dir, lbl_dir, conf=args.conf)
        print(f"  {subset:12s} recall={r['recall']:.3f}  boxes={r['boxes']}  conf={r['mean_conf_of_matches']}")
        for k in ("tiny(<5%)", "small(5-15%)", "mid(15-35%)", "large(>35%)"):
            print(f"      {k:12s} {r[k]}")


if __name__ == "__main__":
    main()
