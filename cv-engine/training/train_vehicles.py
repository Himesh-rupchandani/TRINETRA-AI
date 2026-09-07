#!/usr/bin/env python3
"""Fine-tune YOLO11s on the TRINETRA vehicle dataset.

    python training/train_vehicles.py \\
        --model models/original/yolo11s.pt \\
        --imgsz 960 --epochs 80 --batch 8 --device 0

Never overwrites models/original/. Best weights land at
models/trained/vehicles/best.pt.

Why these defaults (Gujarat elevated CCTV, many small vehicles):

* yolo11s, not n (need small-object recall) and not m/l (hackathon CPU).
* imgsz 960 — 640 collapses far motorcycles to a handful of pixels.
* Fine-tune (pretrained=True, freeze=10) — 100-ish frames is not enough
  to train a detector from scratch.
* AdamW lr0=0.001 — an order of magnitude below from-scratch SGD.
* mosaic + scale for small objects; rotation ≤ 5° (fixed pole camera);
  fliplr OK for vehicles; no vertical flip.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from common import (
    ORIGINAL_VEHICLE,
    RUNS,
    TRAINED_VEHICLE,
    VEHICLE_DS,
    ensure_dirs,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=str(ORIGINAL_VEHICLE if ORIGINAL_VEHICLE.is_file() else "yolo11s.pt"))
    ap.add_argument("--data", default=str(VEHICLE_DS / "data.yaml"))
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--patience", type=int, default=20)
    ap.add_argument("--lr0", type=float, default=0.001)
    ap.add_argument("--freeze", type=int, default=10, help="freeze first N layers (0 = none)")
    ap.add_argument("--project", default=str(RUNS))
    ap.add_argument("--name", default="vehicles")
    args = ap.parse_args()
    ensure_dirs()

    data = Path(args.data)
    if not data.is_file():
        raise SystemExit(f"missing {data} — run extract_frames.py then auto_label.py")

    from ultralytics import YOLO
    from detection.model_paths import backup_original

    model = YOLO(args.model)
    # Keep a pristine copy of the stock weights before any fine-tune.
    src = Path(args.model)
    if src.is_file() and "trained" not in src.parts:
        backup_original(src)

    print(
        f"[train vehicles] model={args.model} data={data} "
        f"imgsz={args.imgsz} epochs={args.epochs} batch={args.batch} device={args.device}"
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
        freeze=args.freeze if args.freeze > 0 else None,
        hsv_h=0.015,
        hsv_s=0.50,
        hsv_v=0.40,          # day/night/rain brightness
        degrees=5.0,         # fixed CCTV pole — tiny roll only
        translate=0.08,
        scale=0.60,          # small-object emphasis
        shear=0.0,
        perspective=0.0004,
        flipud=0.0,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.05,
        copy_paste=0.0,
        erasing=0.15,        # occlusion by other vehicles / rickshaws
        close_mosaic=10,
        plots=True,
    )

    run_best = Path(args.project) / args.name / "weights" / "best.pt"
    last = Path(args.project) / args.name / "weights" / "last.pt"
    TRAINED_VEHICLE.parent.mkdir(parents=True, exist_ok=True)
    if run_best.is_file():
        shutil.copy2(run_best, TRAINED_VEHICLE)
        print(f"[ok] saved {TRAINED_VEHICLE}")
    elif last.is_file():
        shutil.copy2(last, TRAINED_VEHICLE)
        print(f"[ok] saved last.pt -> {TRAINED_VEHICLE}")
    else:
        print("[warn] ultralytics did not write weights/best.pt")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
