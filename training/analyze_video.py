"""
Part 2 — analyse a real traffic/CCTV video before deciding what to train.

Nothing about the footage is assumed. Every figure printed here is measured
from the file itself with OpenCV plus the project's *existing* YOLO11 vehicle
detector, so the training decision is grounded in the video the application
will actually process.

    python training/analyze_video.py /path/to/CAM1.mp4 \
        --model TRINETRAAI/backend/models/yolo11s.pt --sample-every 15

Outputs a JSON report (``training/reports/<stem>_footage.json``) and a
human-readable summary.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = REPO_ROOT / "TRINETRAAI" / "backend" / "models" / "yolo11s.pt"
VEHICLE_CLASS_IDS = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def blur_score(gray: np.ndarray) -> float:
    """Variance of Laplacian — the standard sharpness/motion-blur proxy."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def summarise(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"count": 0}
    vs = sorted(values)
    return {
        "count": len(vs),
        "min": round(vs[0], 4),
        "p10": round(vs[int(0.10 * (len(vs) - 1))], 4),
        "median": round(statistics.median(vs), 4),
        "p90": round(vs[int(0.90 * (len(vs) - 1))], 4),
        "max": round(vs[-1], 4),
        "mean": round(statistics.fmean(vs), 4),
    }


def analyse(video: Path, model_path: Path, sample_every: int, max_samples: int,
            conf: float, imgsz: int) -> dict:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"Cannot open {video}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
    codec = "".join(chr((fourcc >> (8 * i)) & 0xFF) for i in range(4)).strip() or "?"

    detector = None
    if model_path and Path(model_path).is_file():
        from ultralytics import YOLO

        detector = YOLO(str(model_path))
        print(f"[analyze] using detector {model_path}")
    else:
        print(f"[analyze] WARNING: {model_path} not found — geometry stats will be skipped")

    frame_area = float(width * height) if width and height else 0.0
    brightness, blur, sat = [], [], []
    per_frame_counts: List[int] = []
    class_counts: Dict[str, int] = {}
    rel_areas: List[float] = []
    heights_px: List[float] = []
    conf_values: List[float] = []
    overlaps: List[float] = []
    occluded_frames = 0
    y_centres: List[float] = []
    plate_est_heights: List[float] = []

    idx = 0
    sampled = 0
    while sampled < max_samples:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        if idx % sample_every != 0:
            idx += 1
            continue
        idx += 1
        sampled += 1

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        brightness.append(float(gray.mean()))
        blur.append(blur_score(gray))
        sat.append(float(hsv[:, :, 1].mean()))

        if detector is None:
            continue
        res = detector.predict(frame, verbose=False, conf=conf, imgsz=imgsz,
                               device="cpu", classes=list(VEHICLE_CLASS_IDS.keys()))
        boxes = []
        if res and res[0].boxes is not None:
            b = res[0].boxes
            for xyxy, c, k in zip(b.xyxy.cpu().numpy(), b.conf.cpu().numpy(), b.cls.cpu().numpy()):
                name = VEHICLE_CLASS_IDS.get(int(k))
                if name is None:
                    continue
                x1, y1, x2, y2 = [float(v) for v in xyxy]
                boxes.append((x1, y1, x2, y2))
                class_counts[name] = class_counts.get(name, 0) + 1
                conf_values.append(float(c))
                bw, bh = x2 - x1, y2 - y1
                if frame_area:
                    rel_areas.append((bw * bh) / frame_area)
                heights_px.append(bh)
                y_centres.append(((y1 + y2) / 2.0) / max(height, 1))
                # Indian plates are ~0.52 m wide on a ~1.8 m wide car: the
                # plate is roughly 25-30 % of the vehicle box width, and ~1/5
                # of that in height. This is a geometric estimate, clearly
                # labelled as such — not a measurement.
                plate_est_heights.append(bh * 0.11)
        per_frame_counts.append(len(boxes))
        frame_overlap = 0.0
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                v = iou(boxes[i], boxes[j])
                if v > 0:
                    overlaps.append(v)
                frame_overlap = max(frame_overlap, v)
        if frame_overlap >= 0.15:
            occluded_frames += 1

    cap.release()

    night = statistics.fmean(brightness) < 70 if brightness else False
    low_sat = statistics.fmean(sat) < 40 if sat else False
    blur_stats = summarise(blur)
    report = {
        "video": str(video),
        "analysed_at": datetime.now(timezone.utc).isoformat(),
        "container": {
            "resolution": f"{width}x{height}",
            "width": width,
            "height": height,
            "fps": round(fps, 3),
            "frame_count": total,
            "duration_sec": round(total / fps, 2) if total else None,
            "codec": codec,
        },
        "sampling": {"sample_every_n_frames": sample_every, "frames_sampled": sampled},
        "lighting": {
            "mean_brightness_0_255": round(statistics.fmean(brightness), 2) if brightness else None,
            "brightness": summarise(brightness),
            "mean_saturation": round(statistics.fmean(sat), 2) if sat else None,
            "likely_night_or_lowlight": bool(night),
            "likely_greyscale_or_ir": bool(low_sat),
        },
        "sharpness": {
            "laplacian_variance": blur_stats,
            "motion_blur_risk": (
                "high" if blur_stats.get("median", 999) < 60 else
                "medium" if blur_stats.get("median", 999) < 150 else "low"
            ),
        },
        "traffic": {
            "vehicles_per_frame": summarise([float(c) for c in per_frame_counts]),
            "class_distribution": class_counts,
            "classes_present": sorted(class_counts.keys()),
            "detection_confidence": summarise(conf_values),
            "density": (
                "heavy" if per_frame_counts and statistics.fmean(per_frame_counts) >= 8 else
                "moderate" if per_frame_counts and statistics.fmean(per_frame_counts) >= 3 else
                "light"
            ),
        },
        "geometry": {
            "vehicle_box_height_px": summarise(heights_px),
            "vehicle_relative_area": summarise(rel_areas),
            "small_object_fraction": round(
                sum(1 for a in rel_areas if a < 0.01) / len(rel_areas), 4
            ) if rel_areas else None,
            "vertical_centre_normalised": summarise(y_centres),
            "camera_angle_hint": _angle_hint(y_centres, rel_areas),
        },
        "occlusion": {
            "pairwise_iou": summarise(overlaps),
            "frames_with_overlap_ge_015_pct": round(
                100.0 * occluded_frames / max(sampled, 1), 2
            ),
        },
        "plate_estimate": {
            "note": (
                "Geometric estimate from the vehicle box (plate height is about "
                "11 % of a vehicle bounding-box height). Not a measurement."
            ),
            "estimated_plate_height_px": summarise(plate_est_heights),
            "fraction_below_16px": round(
                sum(1 for h in plate_est_heights if h < 16) / len(plate_est_heights), 4
            ) if plate_est_heights else None,
        },
    }
    report["recommendations"] = _recommend(report)
    return report


def _angle_hint(y_centres: List[float], rel_areas: List[float]) -> str:
    if not y_centres:
        return "unknown"
    mean_y = statistics.fmean(y_centres)
    if mean_y > 0.62:
        return "low-mounted / near-eye-level camera (vehicles fill the lower frame)"
    if mean_y < 0.42:
        return "high-mounted / steep downward pole camera"
    return "typical traffic-pole geometry (~4-7 m, moderate downward tilt)"


def _recommend(r: dict) -> List[str]:
    out: List[str] = []
    geo = r["geometry"]
    small = geo.get("small_object_fraction")
    if small is not None and small > 0.35:
        out.append(
            f"{small:.0%} of vehicles occupy <1 % of the frame — keep inference at "
            "imgsz>=960 for far vehicles, or tile the frame."
        )
    pe = r["plate_estimate"].get("fraction_below_16px")
    if pe is not None and pe > 0.4:
        out.append(
            f"~{pe:.0%} of plates are estimated below 16 px tall — a dedicated plate "
            "detector plus super-resolution before OCR is the highest-value change."
        )
    if r["sharpness"]["motion_blur_risk"] != "low":
        out.append("Noticeable motion blur — include blur augmentation in training.")
    if r["lighting"]["likely_night_or_lowlight"]:
        out.append("Low-light footage — include HSV-value augmentation and CLAHE preprocessing.")
    occ = r["occlusion"]["frames_with_overlap_ge_015_pct"]
    if occ > 25:
        out.append(
            f"{occ}% of frames contain overlapping vehicles — lower the NMS IoU "
            "(0.5-0.6) so touching vehicles are not merged."
        )
    conf = r["traffic"]["detection_confidence"]
    if conf.get("count"):
        out.append(
            f"Baseline detector confidence: median {conf['median']}, p10 {conf['p10']} — "
            f"a conf threshold of ~{max(0.20, round(conf['p10'] - 0.05, 2))} keeps far vehicles."
        )
    classes = r["traffic"]["classes_present"]
    out.append(f"Vehicle classes actually present: {', '.join(classes) or 'none detected'}.")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyse real traffic footage (Part 2).")
    ap.add_argument("video", type=Path)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--sample-every", type=int, default=15)
    ap.add_argument("--max-samples", type=int, default=120)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    report = analyse(args.video, args.model, args.sample_every, args.max_samples,
                     args.conf, args.imgsz)
    out = args.out or (Path(__file__).parent / "reports" / f"{args.video.stem}_footage.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))

    c = report["container"]
    print("\n=== FOOTAGE ANALYSIS ===")
    print(f"file            : {args.video.name}")
    print(f"resolution/fps  : {c['resolution']} @ {c['fps']} fps  ({c['duration_sec']}s, codec {c['codec']})")
    print(f"lighting        : mean {report['lighting']['mean_brightness_0_255']}/255"
          f"  night={report['lighting']['likely_night_or_lowlight']}"
          f"  greyscale/IR={report['lighting']['likely_greyscale_or_ir']}")
    print(f"sharpness       : laplacian median {report['sharpness']['laplacian_variance'].get('median')}"
          f"  (motion-blur risk: {report['sharpness']['motion_blur_risk']})")
    print(f"traffic density : {report['traffic']['density']}"
          f"  vehicles/frame median {report['traffic']['vehicles_per_frame'].get('median')}")
    print(f"classes present : {report['traffic']['class_distribution']}")
    print(f"vehicle height  : median {report['geometry']['vehicle_box_height_px'].get('median')} px"
          f"  small(<1% area) {report['geometry']['small_object_fraction']}")
    print(f"camera geometry : {report['geometry']['camera_angle_hint']}")
    print(f"overlap         : {report['occlusion']['frames_with_overlap_ge_015_pct']}% of frames,"
          f" median IoU {report['occlusion']['pairwise_iou'].get('median')}")
    print(f"plate size est. : median {report['plate_estimate']['estimated_plate_height_px'].get('median')} px,"
          f" below 16px {report['plate_estimate']['fraction_below_16px']}")
    print("\nrecommendations :")
    for line in report["recommendations"]:
        print(f"  - {line}")
    print(f"\nreport written to {out}")


if __name__ == "__main__":
    main()
