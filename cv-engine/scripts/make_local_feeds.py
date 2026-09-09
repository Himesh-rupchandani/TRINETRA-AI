#!/usr/bin/env python3
"""
Generate LOCAL DEMO FEED videos for the cv-engine feed demo.

Real traffic footage is not shippable in this repo and external video hosts
are unreachable from the sandbox, so we synthesise clearly-labelled CCTV-style
clips from the project's own sample stills (trinetra-ai/public/cctv/*.jpg):

  segment per still → plate sprite on a real detected car → slow zoom-in with
  pan + sensor jitter/flicker (25 fps, ~9 s) → .mp4 per demo camera.

Pasted plates deliberately include watchlist entries (GJ 01 AB 1234 stolen,
MH 02 CD 5678 wanted) so the ANPR → event → alert chain fires for real, with
clean plates mixed in for realism.

    python scripts/make_local_feeds.py            # writes cv-engine/feeds/*.mp4
    python scripts/make_local_feeds.py --dry-run  # plate paste report only
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import cv2
import numpy as np

CV_ROOT = Path(__file__).resolve().parents[1]
STILLS = CV_ROOT.parent / "trinetra-ai" / "public" / "cctv"
FEEDS_DIR = CV_ROOT / "feeds"
WEIGHTS = CV_ROOT.parent / "trinetra_detection" / "models" / "yolo11n.pt"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

W, H, FPS = 1280, 720, 25
SEG_SECONDS = 9
VEHICLE_CLASSES = {2, 3, 5, 7}

# feed file -> (image names, per-image plate assignments)
FEED_PLANS = {
    "highway2.mp4": (
        ["cctv-01.jpg", "cctv-03.jpg", "cctv-05.jpg"],
        [
            {"car": "GJ 01 AB 1234"},   # STOLEN (watchlist)
            {"car": "GJ 10 KL 7788"},   # clean plate
            {"car": "MH 12 XY 4567"},   # clean plate
        ],
    ),
    "city_cctv.mp4": (
        ["cctv-02.jpg", "cctv-04.jpg", "cctv-06.jpg"],
        [
            {"car": "MH 02 CD 5678"},   # WANTED (watchlist)
            {"car": "TS 09 QR 1122"},   # clean plate
            {"car": "GJ 01 AB 1234"},   # the stolen car continues here
        ],
    ),
}

_MODEL = None


def model():
    global _MODEL
    if _MODEL is None:
        from ultralytics import YOLO

        _MODEL = YOLO(str(WEIGHTS))
    return _MODEL


def normalize_still(img_path: Path) -> np.ndarray:
    src = cv2.imread(str(img_path))
    if src is None:
        raise SystemExit(f"missing still: {img_path}")
    sh, sw = src.shape[:2]
    scale = W / sw
    src = cv2.resize(src, (W, int(round(sh * scale))))
    if src.shape[0] < H:
        canvas = np.full((H, W, 3), 18, dtype=np.uint8)
        y0 = (H - src.shape[0]) // 2
        canvas[y0 : y0 + src.shape[0], :] = src
        src = canvas
    else:
        y0 = (src.shape[0] - H) // 2
        src = src[y0 : y0 + H]
    return src


def plate_sprite(text: str, target_w: int, target_h: int) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(FONT, 64)
    pad = 10
    probe = Image.new("RGB", (10, 10))
    l, t, r, b = ImageDraw.Draw(probe).textbbox((0, 0), text, font=font)
    tw, th = r - l, b - t
    img = Image.new("RGB", (tw + pad * 2, th + pad * 2), (245, 245, 245))
    d = ImageDraw.Draw(img)
    d.text((pad, pad - 4), text, font=font, fill=(15, 15, 15))
    d.rectangle([0, 0, img.width - 1, img.height - 1], outline=(40, 40, 40), width=4)
    d.line([4, img.height - 7, img.width - 5, img.height - 7], fill=(30, 90, 190), width=3)
    out = np.array(img)[:, :, ::-1]
    return cv2.resize(out, (max(40, target_w), max(14, target_h)), interpolation=cv2.INTER_AREA)


def paste_plate(frame: np.ndarray, bbox, plate_text: str) -> bool:
    x1, y1, x2, y2 = (int(v) for v in bbox)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
    bw, bh = x2 - x1, y2 - y1
    if bw < 90 or bh < 60:
        return False
    pw = int(bw * 0.62)
    ph = int(pw * 0.30)
    px = x1 + (bw - pw) // 2
    py = y2 - int(ph * 1.25)
    if py - y1 < bh * 0.35:  # keep it in the lower portion of the vehicle
        py = y1 + int(bh * 0.62)
    py = min(py, frame.shape[0] - ph - 2)
    sprite = plate_sprite(plate_text, pw, ph)
    frame[py : py + ph, px : px + pw] = sprite
    return True


def choose_cars(boxes, frame_h: int, n: int = 1):
    cands = []
    for b in boxes:
        x1, y1, x2, y2 = b
        if (y1 + y2) / 2 < frame_h * 0.30:  # skip far-away traffic
            continue
        bw, bh = max(1, x2 - x1), max(1, y2 - y1)
        if bw / bh < 0.9:  # skip motorcycles / narrow blobs
            continue
        cands.append((bw * bh, b))
    cands.sort(reverse=True)
    return [b for _, b in cands[:n]]


def frame_at(src_plated: np.ndarray, i: int, n: int, rng: random.Random) -> np.ndarray:
    """One animated frame: push-in + drift + jitter, computed on the fly."""
    t = i / max(1, n - 1)
    z = 1.0 + 0.10 * t
    zw, zh = int(W * z), int(H * z)
    big = cv2.resize(src_plated, (zw, zh), interpolation=cv2.INTER_LINEAR)
    px = int((t - 0.5) * 2 * 0.025 * W) + rng.randint(-2, 2)
    py = int(round(0.004 * H * np.sin(2 * np.pi * t * 2))) + rng.randint(-2, 2)
    cx = max(0, min(zw - W, (zw - W) // 2 + px))
    cy = max(0, min(zh - H, (zh - H) // 2 + py))
    fr = big[cy : cy + H, cx : cx + W].astype(np.float32)
    fr += rng.randint(-4, 4)                                   # flicker
    if i % 3 == 0:                                             # cheap sensor noise
        fr += np.random.default_rng(rng.randrange(1 << 31)).normal(0, 2.2, fr.shape[:2])[:, :, None]
    return np.clip(fr, 0, 255).astype(np.uint8)


def prepare_segment(img_path: Path, plates: dict) -> np.ndarray:
    src = normalize_still(img_path)
    if plates.get("car"):
        res = model().predict(src, verbose=False, imgsz=640, classes=list(VEHICLE_CLASSES))[0]
        boxes = res.boxes.xyxy.cpu().numpy().astype(int) if res.boxes is not None else []
        cars = choose_cars(boxes, H, n=1)
        status = paste_plate(src, cars[0], plates["car"]) if cars else False
        print(f"    plate '{plates['car']}' → {'ok' if status else 'SKIP (no suitable car)'}")
    return src


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    n_seg = SEG_SECONDS * FPS
    for out_name, (stills, plate_plan) in FEED_PLANS.items():
        print(f"[FEED] {out_name}: {', '.join(stills)}")
        if args.dry_run:
            for still, plates in zip(stills, plate_plan):
                prepare_segment(STILLS / still, plates or {})
            continue
        FEEDS_DIR.mkdir(parents=True, exist_ok=True)
        out = FEEDS_DIR / out_name
        vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
        if not vw.isOpened():
            out = out.with_suffix(".avi")
            vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (W, H))
        total = 0
        for seg_i, (still, plates) in enumerate(zip(stills, plate_plan)):
            src = prepare_segment(STILLS / still, plates or {})
            rng = random.Random(1000 + seg_i)
            for i in range(n_seg):
                vw.write(frame_at(src, i, n_seg, rng))
                total += 1
        vw.release()
        print(f"  → wrote {out} ({total} frames, {total / FPS:.1f}s)")


if __name__ == "__main__":
    main()
