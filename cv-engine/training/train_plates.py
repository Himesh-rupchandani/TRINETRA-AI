#!/usr/bin/env python3
"""Train a 1-class YOLO11n plate detector on plate boxes.

    python training/train_plates.py --model yolo11n.pt --imgsz 640 --epochs 80 --device 0

Separate from vehicle detection on purpose: a vehicle box is not a plate.
Horizontal flip is DISABLED (it reverses Gujarati/Latin plate characters).
imgsz 640 is enough because we run this model on a vehicle crop, not the
full 1376-px frame.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from common import PLATE_DS, RUNS, TRAINED_PLATE, ensure_dirs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="yolo11n.pt")
    ap.add_argument("--data", default=str(PLATE_DS / "data.yaml"))
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--patience", type=int, default=20)
    ap.add_argument("--lr0", type=float, default=0.001)
    ap.add_argument("--project", default=str(RUNS))
    ap.add_argument("--name", default="plates")
    args = ap.parse_args()
    ensure_dirs()

    data = Path(args.data)
    if not data.is_file():
        raise SystemExit(f"missing {data} — run auto_label.py (and review plate boxes)")

    from ultralytics import YOLO

    model = YOLO(args.model)
    print(
        f"[train plates] model={args.model} data={data} "
        f"imgsz={args.imgsz} epochs={args.epochs} device={args.device}"
    )
    model.train(
        data=str(data),
        imgsz=args.imgsz,
        epochs=args.epochs,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        project=args.project,
        name=args.name,
        exist_ok=True,
        pretrained=True,
        optimizer="AdamW",
        lr0=args.lr0,
        lrf=0.01,
        cos_lr=True,
        hsv_h=0.01,
        hsv_s=0.40,
        hsv_v=0.40,
        degrees=3.0,
        translate=0.05,
        scale=0.40,
        shear=0.0,
        perspective=0.0,     # warping plate text hurts OCR later
        flipud=0.0,
        fliplr=0.0,          # NEVER flip plates
        mosaic=0.5,
        mixup=0.0,
        copy_paste=0.0,
        erasing=0.05,
        close_mosaic=10,
        plots=True,
    )
    run_best = Path(args.project) / args.name / "weights" / "best.pt"
    TRAINED_PLATE.parent.mkdir(parents=True, exist_ok=True)
    if run_best.is_file():
        shutil.copy2(run_best, TRAINED_PLATE)
        print(f"[ok] saved {TRAINED_PLATE}")
        return 0
    print("[warn] no best.pt written")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
