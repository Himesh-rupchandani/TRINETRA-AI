#!/usr/bin/env python3
"""
Synthetic multi-scale Indian number-plate dataset generator.

Why: the repo's fine-tuned plate detector (trinetra_detection/models/best.pt)
was trained on dashcam-like SCENES and is effectively blind when given a
zoomed-in vehicle CROP (0 detections at any scale — measured 2026-09 on real
footage). This generator produces plates at EVERY scale — from 3% of the frame
(far traffic) to 80% (close-up crops) — with realistic Indian layouts and
heavy photometric augmentation, so a model fine-tuned on it stays accurate at
all distances.

Layouts rendered (as seen on Indian roads):
  * white private plate, single line:   GJ 03 PC 3535
  * white private plate with IND strip
  * yellow commercial plate, two lines: GJ 03 PC / 3535   (the hard case)
  * yellow commercial plate, single line
  * green EV plate (rare)

Augmentation per image: gradient/texture background with distractor shapes,
rotation +-7deg, perspective shear, motion blur, gaussian blur, brightness /
contrast / gamma jitter, sensor noise, JPEG artifacts, optional dirt speckles
and a partial occlusion bar.

Output layout (YOLO format):
  <out>/images/{train,val_main,val_closeup,val_tiny}
  <out>/labels/{train,val_main,val_closeup,val_tiny}

Usage:
    python training/generate_synthetic_plates.py --out /tmp/anpr_synth \
        --train 750 --val-main 150 --val-closeup 80 --val-tiny 80 --seed 7
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

STATES = ["GJ", "MH", "DL", "KA", "RJ", "UP", "PB", "TN", "WB", "HR", "MP", "GJ"]
WHITE_BG = (235, 235, 232)
YELLOW_BG = (30, 190, 245)      # BGR of #F5BE1E-ish yellow
GREEN_BG = (60, 160, 60)
BLACK = (15, 15, 15)


def _rand_plate_text(rng: random.Random) -> Tuple[str, str]:
    """(line1, line2) — line2 empty for single-line plates."""
    state = rng.choice(STATES)
    dd = f"{rng.randint(1, 99):02d}"
    letters = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(rng.choice([1, 2, 2, 2])))
    num = f"{rng.randint(0, 9999):04d}"
    style = rng.random()
    if style < 0.45:                      # white private, single line
        return f"{state} {dd} {letters} {num}", ""
    if style < 0.70:                      # yellow commercial, two lines
        return f"{state} {dd} {letters}", num
    if style < 0.85:                      # yellow commercial, single line
        return f"{state} {dd} {letters} {num}", ""
    if style < 0.95:                      # compact private (1 digit district)
        return f"{state} {rng.randint(1, 9)} {letters} {num}", ""
    return f"{state} {dd} {letters} {num}", ""   # filler


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_w: int,
              start_size: int) -> ImageFont.FreeTypeFont:
    """Largest font size <= start_size whose rendering fits max_w."""
    size = start_size
    while size > 8:
        f = ImageFont.truetype(FONT, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return ImageFont.truetype(FONT, 8)


def _draw_char_jittered(draw: ImageDraw.ImageDraw, xy: Tuple[int, int], text: str,
                        font: ImageFont.FreeTypeFont, fill, rng: random.Random) -> None:
    x, y = xy
    for ch in text:
        dy = rng.randint(-1, 1)
        draw.text((x, y + dy), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font)


def render_plate(rng: random.Random) -> np.ndarray:
    """Render one Indian plate (BGR, black border) — no augmentation here."""
    line1, line2 = _rand_plate_text(rng)
    two_line = bool(line2)
    yellow = rng.random() < 0.45
    ev = (not yellow) and rng.random() < 0.10
    bg = YELLOW_BG if yellow else (GREEN_BG if ev else WHITE_BG)
    fg = BLACK if not ev else (240, 245, 240)

    w = rng.randint(300, 460)
    h = int(w / (1.75 if two_line else 2.25))
    pad = max(6, w // 40)
    img = np.full((h, w, 3), bg, dtype=np.uint8)
    if yellow:
        img[: max(2, h // 14)] = (20, 20, 20)          # top strip like commercial plates

    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)

    if two_line:
        raw1, raw2 = line1.replace(" ", ""), line2
        f1 = _fit_font(draw, raw1, int(w * 0.88), int(h * 0.34))
        f2 = _fit_font(draw, raw2, int(w * 0.88), int(h * 0.40))
        l1w = draw.textlength(raw1, font=f1)
        _draw_char_jittered(draw, (int((w - l1w) / 2), int(h * 0.06)), raw1, f1, fg, rng)
        l2w = draw.textlength(raw2, font=f2)
        _draw_char_jittered(draw, (int((w - l2w) / 2), int(h * 0.52)), raw2, f2, fg, rng)
    else:
        spaced = line1 if rng.random() < 0.55 else line1.replace(" ", "")
        font = _fit_font(draw, spaced, int(w * 0.9), int(h * 0.52))
        tw = draw.textlength(spaced, font=font)
        _draw_char_jittered(draw, (int((w - tw) / 2), int((h - font.size) / 2)), spaced, font, fg, rng)

    img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), BLACK, thickness=max(2, w // 130))
    return img


def _photometric(img: np.ndarray, rng: random.Random) -> np.ndarray:
    if rng.random() < 0.7:                      # brightness / contrast
        a = rng.uniform(0.7, 1.3)
        b = rng.uniform(-30, 30)
        img = np.clip(img.astype(np.float32) * a + b, 0, 255).astype(np.uint8)
    if rng.random() < 0.5:                      # gamma
        g = rng.uniform(0.6, 1.6)
        lut = np.array([((i / 255.0) ** g) * 255 for i in range(256)]).astype(np.uint8)
        img = cv2.LUT(img, lut)
    if rng.random() < 0.45:                     # motion blur
        k = rng.choice([3, 5, 7, 9])
        kern = np.zeros((k, k), np.float32)
        kern[k // 2, :] = 1.0 / k
        if rng.random() < 0.5:
            kern = kern.T
        img = cv2.filter2D(img, -1, kern)
    if rng.random() < 0.4:                      # gaussian blur
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.4, 1.6))
    if rng.random() < 0.5:                      # sensor noise
        n = np.random.normal(0, rng.uniform(3, 12), img.shape).astype(np.float32)
        img = np.clip(img.astype(np.float32) + n, 0, 255).astype(np.uint8)
    q = rng.randint(38, 95)                     # JPEG artifacts
    ok, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), q])
    if ok:
        img = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    return img


def _plate_damage(plate: np.ndarray, rng: random.Random) -> np.ndarray:
    h, w = plate.shape[:2]
    if rng.random() < 0.30:                     # dirt speckles
        for _ in range(rng.randint(4, 18)):
            x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
            r = rng.randint(1, max(2, w // 60))
            col = int(rng.randint(60, 200))
            cv2.circle(plate, (x, y), r, (col, col, col), -1)
    if rng.random() < 0.12:                     # partial occlusion bar
        bh = int(h * rng.uniform(0.15, 0.3))
        y0 = rng.randint(0, h - bh)
        shade = int(rng.randint(90, 180))
        plate[y0:y0 + bh, :] = (shade, shade, shade)
    return plate


def _background(w: int, h: int, rng: random.Random) -> np.ndarray:
    c1 = np.full((h, w, 3), rng.randint(35, 90), np.uint8)
    c2 = np.full((h, w, 3), rng.randint(90, 170), np.uint8)
    alpha = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    img = (c1 * (1 - alpha) + c2 * alpha).astype(np.uint8)
    for _ in range(rng.randint(3, 10)):          # distractor "vehicles"/structures
        x0, y0 = rng.randint(0, w - 1), rng.randint(0, h - 1)
        x1, y1 = min(w, x0 + rng.randint(30, w // 2)), min(h, y0 + rng.randint(20, h // 2))
        col = (rng.randint(30, 200), rng.randint(30, 200), rng.randint(30, 200))
        cv2.rectangle(img, (x0, y0), (x1, y1), col, -1)
    if rng.random() < 0.6:
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(1.0, 4.0))
    n = np.random.normal(0, rng.uniform(2, 8), img.shape).astype(np.float32)
    return np.clip(img.astype(np.float32) + n, 0, 255).astype(np.uint8)


def _paste(scene: np.ndarray, plate: np.ndarray, rng: random.Random,
           scale: float) -> Tuple[int, int, int, int]:
    """Paste `plate` scaled so its width = scale*scene width, with rotation and
    shear. Returns the axis-aligned (x1, y1, x2, y2) in scene coordinates."""
    H, W = scene.shape[:2]
    pw = max(24, int(scale * W))
    ph = max(12, int(pw * plate.shape[0] / plate.shape[1]))
    p = cv2.resize(plate, (pw, ph), interpolation=cv2.INTER_AREA if scale < 0.2 else cv2.INTER_LINEAR)

    ang = rng.uniform(-7, 7)
    M = cv2.getRotationMatrix2D((pw / 2, ph / 2), ang, 1.0)
    M[0, 2] += rng.uniform(0.0, 0.06) * pw      # shear-ish
    cos, sin = abs(M[0, 0]), abs(M[1, 0])
    bw, bh = int(pw * cos + ph * sin), int(pw * sin + ph * cos)
    M[0, 2] += (bw - pw) / 2
    M[1, 2] += (bh - ph) / 2
    warped = cv2.warpAffine(p, M, (bw, bh), borderValue=(0, 0, 0))

    mask = warped.max(axis=2) > 0
    x0 = rng.randint(0, max(0, W - bw))
    y0 = rng.randint(0, max(0, H - bh))
    x1, y1 = min(W, x0 + bw), min(H, y0 + bh)
    roi = scene[y0:y1, x0:x1]
    wregion = warped[: roi.shape[0], : roi.shape[1]]
    mregion = mask[: roi.shape[0], : roi.shape[1]]
    roi[mregion] = wregion[mregion]
    scene[y0:y1, x0:x1] = roi
    return x0, y0, x0 + roi.shape[1], y0 + roi.shape[0]


def make_image(rng: random.Random, out_w: int, out_h: int,
               mode: str) -> Tuple[np.ndarray, Optional[Tuple[int, int, int, int]]]:
    scene = _background(out_w, out_h, rng)
    if mode == "empty":
        return _photometric(scene, rng), None
    plate = _plate_damage(render_plate(rng).copy(), rng)
    if mode == "scene":
        scale = rng.uniform(0.03, 0.20)
    elif mode == "closeup":
        scale = rng.uniform(0.25, 0.80)
    else:                                       # tiny
        scale = rng.uniform(0.02, 0.06)
    x1, y1, x2, y2 = _paste(scene, plate, rng, scale)
    return _photometric(scene, rng), (x1, y1, x2, y2)


def _write_set(rng: random.Random, out: Path, subset: str, n: int,
               mode_picker) -> None:
    img_dir = out / "images" / subset
    lbl_dir = out / "labels" / subset
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        mode = mode_picker(rng)
        if mode == "empty":
            w, h = rng.choice([(640, 360), (416, 416)])
        elif mode == "closeup":
            w, h = (416, 416)
        else:
            w, h = (640, 360) if rng.random() < 0.8 else (416, 416)
        img, box = make_image(rng, w, h, mode)
        name = f"{subset}_{i:05d}"
        cv2.imwrite(str(img_dir / f"{name}.jpg"), img,
                    [int(cv2.IMWRITE_JPEG_QUALITY), rng.randint(70, 95)])
        if box is None:
            (lbl_dir / f"{name}.txt").write_text("")
        else:
            x1, y1, x2, y2 = box
            xc, yc = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
            bw, bh = (x2 - x1) / w, (y2 - y1) / h
            (lbl_dir / f"{name}.txt").write_text(f"1 {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--train", type=int, default=750)
    ap.add_argument("--val-main", type=int, default=150)
    ap.add_argument("--val-closeup", type=int, default=80)
    ap.add_argument("--val-tiny", type=int, default=80)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    out = Path(args.out)
    if out.exists():
        import shutil
        shutil.rmtree(out)
    rng = random.Random(args.seed)
    np.random.seed(args.seed)

    # train: mixed (60% scene, 25% closeup, 15% empty — tiny appears via scene's low end)
    _write_set(rng, out, "train", args.train,
               lambda r: r.choices(["scene", "closeup", "empty"], weights=[60, 25, 15])[0])
    _write_set(rng, out, "val_main", args.val_main,
               lambda r: r.choices(["scene", "closeup", "empty"], weights=[70, 20, 10])[0])
    _write_set(rng, out, "val_closeup", args.val_closeup, lambda r: "closeup")
    _write_set(rng, out, "val_tiny", args.val_tiny, lambda r: "tiny")
    print(f"dataset written to {out}")


if __name__ == "__main__":
    main()
