#!/usr/bin/env python3
"""
Performance measurement (spec §28).

Measures what can actually be measured on this machine and says so plainly
when something cannot be measured (no GPU here => GPU utilization reported
as 'not measurable').

    python scripts/benchmark.py --video path/to/clip.mp4 --frames 300
    python scripts/benchmark.py --camera cam04 --frames 300     # live
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _pct(vals):
    if not vals:
        return "n/a"
    vals = sorted(vals)
    return (
        f"mean={vals[len(vals)//2]*0+statistics.mean(vals):.1f} "
        f"p50={vals[len(vals)//2]:.1f} p95={vals[min(len(vals)-1, int(len(vals)*0.95))]:.1f} "
        f"max={vals[-1]:.1f}"
    )


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--video", help="local video file")
    src.add_argument("--camera", help="Sentinel camera id (live)")
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--imgsz", type=int, default=None)
    args = ap.parse_args()

    from config.settings import Settings
    from detection.vehicle_detector import VehicleDetector
    from tracking.vehicle_tracker import VehicleTracker
    from anpr.ocr import OcrEngine
    from anpr.plate_detector import extract_plate_candidates, preprocess_for_ocr

    settings = Settings.from_env()
    if args.imgsz:
        settings.inference_imgsz = args.imgsz

    # --- source ---------------------------------------------------------
    if args.video:
        import cv2
        cap = cv2.VideoCapture(args.video)
        pts_source = "file CAP_PROP_POS_MSEC"

        def read():
            ok, fr = cap.read()
            return (fr, float(cap.get(cv2.CAP_PROP_POS_MSEC)) if ok else None)
    else:
        from capture.sentinel_catalogue import SentinelCatalogue
        from capture.reconnect import ManagedCapture

        cat = SentinelCatalogue(url=settings.sentinel_catalogue_url)
        cat.fetch()
        cam = cat.get_camera(args.camera)
        if cam is None:
            raise SystemExit(f"camera {args.camera} not in catalogue")
        managed = ManagedCapture(cam, settings)
        it = managed.packets()
        pts_source = "live stream PTS"

        def read():
            pkt = next(it, None)
            return (pkt.frame, pkt.pts_ms) if pkt else (None, None)

    detector = VehicleDetector(settings.model_path, settings.conf_threshold,
                               settings.inference_imgsz, settings.device)
    detector.warmup()
    tracker = VehicleTracker()
    ocr = OcrEngine(gpu=False)

    det_ms, trk_ms, anpr_ms, gap_ms = [], [], [], []
    frames = 0
    pts_vals = []
    t_start = time.perf_counter()
    last_pts = None

    try:
        while frames < args.frames:
            frame, pts = read()
            if frame is None:
                break
            frames += 1
            if pts is not None:
                pts_vals.append(pts)
                if last_pts is not None and pts > last_pts:
                    gap_ms.append(pts - last_pts)
                last_pts = pts

            t0 = time.perf_counter()
            dets = detector.detect(frame, camera_id="bench", pts_ms=pts)
            det_ms.append((time.perf_counter() - t0) * 1000)

            t0 = time.perf_counter()
            tracks = tracker.update(dets, pts_ms=pts)
            trk_ms.append((time.perf_counter() - t0) * 1000)

            if tracks:
                crops = extract_plate_candidates(frame, tracks[0].bbox, tracks[0].class_name)
                if crops:
                    t0 = time.perf_counter()
                    ocr.read(preprocess_for_ocr(crops[0]))
                    anpr_ms.append((time.perf_counter() - t0) * 1000)
    finally:
        elapsed = time.perf_counter() - t_start

    # --- report -----------------------------------------------------------
    print("=" * 64)
    print(f"TRINETRA cv-engine benchmark — {frames} frames in {elapsed:.1f}s "
          f"({frames / elapsed:.2f} fps end-to-end)" if elapsed else "no frames")
    print(f"PTS source: {pts_source}")
    print(f"detection ms   : {_pct(det_ms)}")
    print(f"tracking ms    : {_pct(trk_ms)}")
    print(f"ANPR (OCR) ms  : {_pct(anpr_ms)}")
    print(f"frame PTS gaps : {_pct(gap_ms)}")
    if pts_vals:
        span = (pts_vals[-1] - pts_vals[0]) / 1000.0
        if span > 0:
            print(f"delivered rate : {(len(pts_vals)-1)/span:.2f} frames/sec (from PTS span {span:.1f}s)")
    print(f"active tracks  : {tracker.active_count()}")

    try:
        import psutil
        p = psutil.Process()
        print(f"memory RSS     : {p.memory_info().rss / 1e6:.0f} MB")
        print(f"CPU utilization: system {psutil.cpu_percent(interval=0.5):.1f}% (process threads: {p.num_threads()})")
    except ImportError:
        print("memory/CPU     : psutil not installed — not measured")

    try:
        import torch
        if torch.cuda.is_available():
            print(f"GPU utilization: {torch.cuda.utilization()}%")  # may be approximate
        else:
            print("GPU utilization: not measurable (CUDA unavailable; running on CPU)")
    except Exception:
        print("GPU utilization: not measurable")


if __name__ == "__main__":
    main()
