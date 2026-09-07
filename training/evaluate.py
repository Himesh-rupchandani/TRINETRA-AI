#!/usr/bin/env python3
"""
PART 6/7 — measure the baseline against the fine-tuned model. No estimates.

Three independent comparisons, each optional:

1. ``--plate-model``  Plate DETECTION on the held-out test split:
   precision / recall / mAP50 / mAP50-95 from Ultralytics, plus FP and FN
   counts and a breakdown by plate size (small = the far vehicles that this
   whole exercise is about). The classical OpenCV proposer is scored on the
   same split with the same IoU rule, so "before" and "after" are comparable.

2. ``--vehicle-model``  Vehicle DETECTION on a labelled vehicle split, same
   metrics — run this only if PART 2 showed the vehicle detector is the weak
   component.

3. ``--ocr-truth``  OCR accuracy on a CSV of ``image,plate`` ground truth:
   exact-match rate, character error rate, and how many reads the confidence
   policy correctly refuses (a refused read is a *good* outcome — it becomes
   Unknown instead of a wrong plate).

Every number printed comes from a comparison performed here. Anything that
could not be measured is printed as ``n/a``, never guessed.

Usage:
    python training/evaluate.py --data training/dataset/plates.yaml \
        --plate-model TRINETRAAI/backend/models/plate_detector.pt \
        --ocr-truth training/ocr_truth.csv --out training/reports/eval.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "TRINETRAAI" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

SMALL_PLATE_PX = 16  # plate height below which OCR is unreliable


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def load_labels(label_path: Path, w: int, h: int) -> List[List[float]]:
    if not label_path.is_file():
        return []
    out = []
    for line in label_path.read_text().strip().splitlines():
        p = line.split()
        if len(p) != 5:
            continue
        _c, cx, cy, bw, bh = int(p[0]), *map(float, p[1:])
        out.append([(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h])
    return out


def match(preds: List[List[float]], gts: List[List[float]], thr: float = 0.5) -> Tuple[int, int, int, List[int]]:
    """Greedy IoU matching -> (tp, fp, fn, matched ground-truth indices)."""
    used, tp, matched = set(), 0, []
    for p in sorted(preds, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1])):
        best, best_i = 0.0, -1
        for i, g in enumerate(gts):
            if i in used:
                continue
            v = iou(p, g)
            if v > best:
                best, best_i = v, i
        if best >= thr:
            used.add(best_i)
            matched.append(best_i)
            tp += 1
    return tp, len(preds) - tp, len(gts) - tp, matched


def prf(tp: int, fp: int, fn: int) -> Dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}


def cer(pred: str, truth: str) -> float:
    """Character error rate (Levenshtein / len(truth))."""
    if not truth:
        return 1.0 if pred else 0.0
    prev = list(range(len(truth) + 1))
    for i, pc in enumerate(pred, 1):
        cur = [i]
        for j, tc in enumerate(truth, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (pc != tc)))
        prev = cur
    return prev[-1] / len(truth)


# --------------------------------------------------------------------------- #
# 1. plate detection
# --------------------------------------------------------------------------- #
def eval_plate_detection(data_yaml: Path, model_path: Optional[Path], split: str = "test") -> dict:
    import yaml

    cfg = yaml.safe_load(data_yaml.read_text())
    root = Path(cfg["path"])
    img_dir = root / cfg.get(split, f"images/{split}")
    images = sorted(img_dir.glob("*.jpg"))
    if not images:
        return {"error": f"no images in {img_dir}"}

    from app.services.plate_detector_service import PlateDetectorService

    classical = PlateDetectorService()          # model-less: classical proposer
    classical._model_attempted, classical._model = True, None
    from app.services.vehicle_detection_service import vehicle_detection_service

    learned = None
    if model_path and model_path.is_file():
        from ultralytics import YOLO

        learned = YOLO(str(model_path))

    agg = {"classical": {"tp": 0, "fp": 0, "fn": 0},
           "finetuned": {"tp": 0, "fp": 0, "fn": 0}}
    small = {"classical": {"tp": 0, "fn": 0}, "finetuned": {"tp": 0, "fn": 0}}

    for img_path in images:
        frame = cv2.imread(str(img_path))
        if frame is None:
            continue
        h, w = frame.shape[:2]
        gts = load_labels(root / "labels" / split / f"{img_path.stem}.txt", w, h)

        # -- classical: proposals inside each detected vehicle
        c_preds = []
        for det in vehicle_detection_service.detect(frame):
            for b in classical.detect(frame, (det.x1, det.y1, det.x2, det.y2),
                                      det.class_name, max_candidates=2):
                if b.source != "heuristic":     # a geometric guess is not a detection
                    c_preds.append([b.x1, b.y1, b.x2, b.y2])

        # -- fine-tuned: whole-frame inference
        f_preds = []
        if learned is not None:
            res = learned.predict(frame, verbose=False, conf=0.25, device="cpu")
            if res and res[0].boxes is not None:
                f_preds = [[float(v) for v in b[:4]] for b in res[0].boxes.xyxy.cpu().numpy()]

        for key, preds in (("classical", c_preds), ("finetuned", f_preds)):
            if key == "finetuned" and learned is None:
                continue
            tp, fp, fn, matched = match(preds, gts)
            agg[key]["tp"] += tp
            agg[key]["fp"] += fp
            agg[key]["fn"] += fn
            for i, g in enumerate(gts):
                if (g[3] - g[1]) >= SMALL_PLATE_PX:
                    continue
                small[key]["tp" if i in matched else "fn"] += 1

    out = {
        "split": split, "images": len(images),
        "classical_opencv": prf(**agg["classical"]),
        "small_plates_classical": prf(small["classical"]["tp"], 0, small["classical"]["fn"]),
    }
    if learned is not None:
        out["finetuned"] = prf(**agg["finetuned"])
        out["small_plates_finetuned"] = prf(small["finetuned"]["tp"], 0, small["finetuned"]["fn"])
        try:  # official mAP from Ultralytics on the same split
            m = learned.val(data=str(data_yaml), split=split, device="cpu", verbose=False)
            out["finetuned_map"] = {
                "mAP50": round(float(m.box.map50), 4),
                "mAP50_95": round(float(m.box.map), 4),
                "precision": round(float(m.box.mp), 4),
                "recall": round(float(m.box.mr), 4),
            }
        except Exception as exc:
            out["finetuned_map"] = {"error": str(exc)}
    else:
        out["finetuned"] = "n/a — no fine-tuned plate model supplied"
    return out


# --------------------------------------------------------------------------- #
# 2. vehicle detection
# --------------------------------------------------------------------------- #
def eval_vehicle_detection(data_yaml: Path, model_path: Path, split: str = "test") -> dict:
    from ultralytics import YOLO

    model = YOLO(str(model_path))
    m = model.val(data=str(data_yaml), split=split, device="cpu", verbose=False)
    return {
        "model": model_path.name,
        "mAP50": round(float(m.box.map50), 4),
        "mAP50_95": round(float(m.box.map), 4),
        "precision": round(float(m.box.mp), 4),
        "recall": round(float(m.box.mr), 4),
    }


# --------------------------------------------------------------------------- #
# 3. OCR accuracy
# --------------------------------------------------------------------------- #
def eval_ocr(truth_csv: Path) -> dict:
    from app.core.config import settings
    from app.services.anpr_pipeline import read_plate_for_vehicle
    from app.utils.plate_normalizer import normalize_plate

    rows = []
    with truth_csv.open(newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("image") and r.get("plate"):
                rows.append((Path(r["image"]), normalize_plate(r["plate"]) or r["plate"].upper()))
    if not rows:
        return {"error": f"no usable rows in {truth_csv} (expected columns: image,plate)"}

    exact = refused = wrong = 0
    cers: List[float] = []
    min_conf = float(getattr(settings, "OCR_MIN_CONFIDENCE", 0.60))
    for img_path, truth in rows:
        p = img_path if img_path.is_absolute() else (truth_csv.parent / img_path)
        frame = cv2.imread(str(p))
        if frame is None:
            continue
        h, w = frame.shape[:2]
        read = read_plate_for_vehicle(frame, (0, 0, w, h), "car")
        if read is None or read.confidence < min_conf:
            refused += 1
            continue
        if read.normalized == truth:
            exact += 1
        else:
            wrong += 1
        cers.append(cer(read.normalized, truth))
    total = len(rows)
    return {
        "samples": total,
        "exact_match": exact,
        "exact_match_rate": round(exact / total, 4) if total else 0.0,
        "wrong_reads": wrong,
        "refused_low_confidence": refused,
        "refusal_rate": round(refused / total, 4) if total else 0.0,
        "mean_character_error_rate": round(float(np.mean(cers)), 4) if cers else None,
        "note": ("A refused read becomes Unknown in the UI. Refusals are safe; "
                 "'wrong_reads' is the only number that can mislead an investigator."),
    }


# --------------------------------------------------------------------------- #
def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(REPO_ROOT / "training/dataset/plates.yaml"))
    ap.add_argument("--split", default="test")
    ap.add_argument("--plate-model", default="")
    ap.add_argument("--vehicle-data", default="")
    ap.add_argument("--vehicle-model", default="")
    ap.add_argument("--ocr-truth", default="")
    ap.add_argument("--out", default=str(REPO_ROOT / "training/reports/evaluation.json"))
    args = ap.parse_args(argv)

    report: Dict[str, object] = {}

    data = Path(args.data)
    if data.is_file():
        report["plate_detection"] = eval_plate_detection(
            data, Path(args.plate_model) if args.plate_model else None, args.split
        )
    else:
        report["plate_detection"] = f"n/a — {data} not found"

    if args.vehicle_model and args.vehicle_data:
        report["vehicle_detection"] = eval_vehicle_detection(
            Path(args.vehicle_data), Path(args.vehicle_model), args.split
        )
    else:
        report["vehicle_detection"] = "n/a — not evaluated (pass --vehicle-data and --vehicle-model)"

    if args.ocr_truth:
        report["ocr"] = eval_ocr(Path(args.ocr_truth))
    else:
        report["ocr"] = "n/a — no ground-truth CSV supplied"

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    print(f"\n[evaluate] report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
