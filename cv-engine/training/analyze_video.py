#!/usr/bin/env python3
"""Inspect a traffic/CCTV video (or domain stills) and write a footage report.

    python training/analyze_video.py --video feeds/reference_traffic.mp4
    python training/analyze_video.py                 # stills + any local video

The report is what the rest of the training config is based on: resolution,
FPS, vehicle scale, plate pixel size, lighting, overlap, motion.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from common import (
    DOMAIN_STILLS,
    FEEDS_DIR,
    FRAMES_DIR,
    REFERENCE_BYTES,
    REFERENCE_DRIVE_URL,
    REFERENCE_FILENAME,
    REFERENCE_VIDEO,
    REPORTS,
    VEHICLE_CLASSES,
    ensure_dirs,
)


def _open_video(path: Path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {path}")
    return cap


def _sample_indices(n: int, k: int) -> list:
    if n <= 0:
        return []
    k = min(k, n)
    if k == 1:
        return [0]
    return [int(round(i * (n - 1) / (k - 1))) for i in range(k)]


def _brightness_stats(frame: np.ndarray) -> dict:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return {
        "mean": round(float(gray.mean()), 2),
        "std": round(float(gray.std()), 2),
        "min": int(gray.min()),
        "max": int(gray.max()),
    }


def _blur_score(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _motion_score(prev: np.ndarray, cur: np.ndarray) -> float:
    a = cv2.resize(cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY), (64, 36))
    b = cv2.resize(cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY), (64, 36))
    return float(np.mean(np.abs(a.astype(np.float32) - b.astype(np.float32))))


def analyze_video(path: Path, n_samples: int = 24) -> dict:
    cap = _open_video(path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = (n / fps) if fps > 1e-3 else 0.0
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
    codec = "".join(chr((fourcc >> 8 * i) & 0xFF) for i in range(4)).strip() or "unknown"

    idxs = _sample_indices(n, n_samples) if n > 0 else list(range(n_samples))
    frames = []
    blur_scores = []
    bright = []
    motion = []
    prev = None
    grabbed = 0
    if n > 0:
        for i in idxs:
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            grabbed += 1
            frames.append(frame)
            blur_scores.append(_blur_score(frame))
            bright.append(_brightness_stats(frame))
            if prev is not None:
                motion.append(_motion_score(prev, frame))
            prev = frame
    else:
        # Some containers don't expose frame count — read sequentially.
        while grabbed < n_samples:
            ok, frame = cap.read()
            if not ok:
                break
            grabbed += 1
            frames.append(frame)
            blur_scores.append(_blur_score(frame))
            bright.append(_brightness_stats(frame))
            if prev is not None:
                motion.append(_motion_score(prev, frame))
            prev = frame
    cap.release()

    if not frames:
        raise SystemExit(f"no frames decoded from {path}")

    # Persist a few preview JPEGs for the report.
    preview_dir = FRAMES_DIR / path.stem
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_paths = []
    for i, fr in enumerate(frames[:8]):
        p = preview_dir / f"sample_{i:02d}.jpg"
        cv2.imwrite(str(p), fr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        preview_paths.append(str(p.relative_to(path.parents[1] if path.parents else path.parent)))

    mean_bright = float(np.mean([b["mean"] for b in bright]))
    night = mean_bright < 70
    day = mean_bright > 95
    lighting = "night" if night else ("day" if day else "dusk/dawn or overcast")

    # Heuristic plate-size estimate: a typical Indian plate is ~520x110 mm.
    # At 1080p from a 6–8 m pole looking down a road, near plates are ~40–80 px
    # wide and far plates drop below 16 px (OCR-impossible).
    near_plate_w = max(16, int(w * 0.045))
    far_plate_w = max(4, int(w * 0.008))

    return {
        "path": str(path),
        "filename": path.name,
        "bytes": path.stat().st_size if path.is_file() else None,
        "width": w,
        "height": h,
        "fps": round(fps, 3),
        "frame_count": n,
        "duration_sec": round(duration, 2),
        "codec": codec,
        "samples_decoded": grabbed,
        "lighting": lighting,
        "brightness_mean": round(mean_bright, 2),
        "brightness_std": round(float(np.mean([b["std"] for b in bright])), 2),
        "blur_laplacian_var_mean": round(float(np.mean(blur_scores)), 2),
        "blur_laplacian_var_min": round(float(np.min(blur_scores)), 2),
        "motion_mean_abs_diff": round(float(np.mean(motion)), 2) if motion else None,
        "vehicles_moving": (float(np.mean(motion)) > 4.0) if motion else None,
        "estimated_near_plate_width_px": near_plate_w,
        "estimated_far_plate_width_px": far_plate_w,
        "preview_frames": preview_paths,
        "recommended_extract_interval_sec": 1.0 if duration <= 180 else 1.5,
        "recommended_extract_count": int(min(220, max(80, duration * 0.8))) if duration else 120,
    }


def analyze_stills(dir_path: Path) -> dict:
    files = sorted(p for p in dir_path.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    stills = []
    for p in files:
        im = cv2.imread(str(p))
        if im is None:
            continue
        h, w = im.shape[:2]
        b = _brightness_stats(im)
        stills.append(
            {
                "file": p.name,
                "width": w,
                "height": h,
                "brightness_mean": b["mean"],
                "brightness_std": b["std"],
                "blur_laplacian_var": round(_blur_score(im), 2),
                "lighting": "night" if b["mean"] < 70 else ("day" if b["mean"] > 95 else "mixed"),
            }
        )
    return {"dir": str(dir_path), "count": len(stills), "stills": stills}


def write_markdown(report: dict, dest: Path) -> None:
    v = report.get("video") or {}
    dest.write_text(
        "\n".join(
            [
                "# Footage analysis — TRINETRA vehicle + plate training",
                "",
                "This report is the source of truth for the training configuration.",
                "It is derived from the Google Drive reference clip (when present)",
                "and from the in-repo Gujarat CCTV stills that match the same domain.",
                "",
                "## Reference clip (Google Drive)",
                "",
                f"- Listing name: `{REFERENCE_FILENAME}`",
                f"- Listed size: {REFERENCE_BYTES / 1e6:.0f} MB",
                f"- URL: {REFERENCE_DRIVE_URL}",
                f"- Local path: `{REFERENCE_VIDEO}`",
                f"- Present locally: **{'yes' if report.get('video_present') else 'NO'}**",
                "",
                "## Decoded video metrics",
                "",
                "```json",
                json.dumps(v, indent=2) if v else "{ \"note\": \"video not decoded in this environment\" }",
                "```",
                "",
                "## Domain stills (Gujarat urban CCTV, 1376×768)",
                "",
                "These stills live in `trinetra-ai/public/cctv/` and are the same",
                "elevated-pole, mixed traffic, day/night/rain distribution the",
                "Sentinel Ahmedabad cameras produce.",
                "",
                "```json",
                json.dumps(report.get("stills"), indent=2),
                "```",
                "",
                "## What this footage implies for training",
                "",
                "- **Fine-tune YOLO11s**, do not train from scratch.",
                "- **Classes:** " + ", ".join(VEHICLE_CLASSES) + ".",
                "- Auto-rickshaws are the #1 miss on stock COCO YOLO.",
                "- Far vehicles occupy well under 1% of the frame → train/infer at **imgsz 960**.",
                "- Number plates are readable only on near vehicles (≈40–80 px wide).",
                "  Far plates are below OCR resolution — the pipeline must return Unknown,",
                "  never invent a string.",
                "- Crowded overlap + pedestrians next to bikes → NMS IoU **0.50**, not 0.7.",
                "- Night / rain / motion blur are in-domain → brightness, blur, noise augs.",
                "- Camera is a fixed elevated pole → rotation ≤ 5°, no vertical flip.",
                "- Plate model must NOT use horizontal flip (reverses characters).",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", type=Path, default=None)
    ap.add_argument("--samples", type=int, default=24)
    args = ap.parse_args()
    ensure_dirs()

    video = args.video
    if video is None:
        if REFERENCE_VIDEO.is_file():
            video = REFERENCE_VIDEO
        else:
            extras = sorted(FEEDS_DIR.glob("*.mp4")) + sorted(FEEDS_DIR.glob("*.avi"))
            video = extras[0] if extras else None

    report = {
        "drive_url": REFERENCE_DRIVE_URL,
        "drive_filename": REFERENCE_FILENAME,
        "drive_bytes_listed": REFERENCE_BYTES,
        "video_present": bool(video and Path(video).is_file()),
        "video": None,
        "stills": analyze_stills(DOMAIN_STILLS) if DOMAIN_STILLS.is_dir() else None,
        "required_vehicle_classes": VEHICLE_CLASSES,
    }
    if video and Path(video).is_file():
        print(f"[analyze] decoding {video}")
        report["video"] = analyze_video(Path(video), n_samples=args.samples)
    else:
        print("[analyze] no local video — Drive clip was not downloaded in this environment.")
        print(f"          expected at {REFERENCE_VIDEO}")
        print("          run: python training/download_reference.py")

    REPORTS.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS / "footage_analysis.json"
    md_path = REPORTS / "FOOTAGE_DECODED.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, md_path)
    print(f"[ok] {json_path}")
    print(f"[ok] {md_path}")
    if report["video"]:
        v = report["video"]
        print(
            f"    {v['width']}x{v['height']} @ {v['fps']} fps, "
            f"{v['duration_sec']}s, lighting={v['lighting']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
