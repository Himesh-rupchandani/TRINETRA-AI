#!/usr/bin/env python3
"""Traffic clips used as camera sources for local testing.

Two modes, and the difference between them matters:

``--source demo_cam04.mp4`` (preferred, and what the Makefile-style command
below uses) re-times, crops and grades REAL footage that already ships in this
repository, so a detector run over it produces real boxes over real vehicles.
``--mode synthetic`` renders a traffic scene from scratch instead - useful when
no footage at all is available, but a COCO detector sees stylized rectangles,
so it exercises the plumbing and not the model.

Either way the caption burned into the frame says the clip is a local test
fixture: it is not evidence, and the camera registry reports it as RECORDED,
never LIVE.

    .venv/bin/python TRINETRAAI/backend/scripts/build_synthetic_test_clips.py \
        --source TRINETRAAI/backend/demo_cam04.mp4 \
        --out-dir TRINETRAAI/backend/uploads/analysis

These are the files the seeded demo cameras (JUNCTION_DAY, NIGHT_BRIDGE,
DENSE_PARKED_BIKES, AVENUE_1080P) point at. They exist so the pipeline, the
live overlay and the plate search can be exercised without anybody's real
footage - and they are recorded fixtures, which the registry now labels
RECORDED rather than LIVE.

They are deliberately rendered with real object boundaries (body, roof,
windows, wheels, lights, plate rectangle) instead of flat coloured blocks: a
box around a flat rectangle tells you nothing about whether the detector is
tight. Nothing here is a demo of accuracy; it is a test pattern that happens to
look like traffic.

    .venv/bin/python TRINETRAAI/backend/scripts/build_synthetic_test_clips.py \
        --out-dir TRINETRAAI/backend/uploads/analysis
"""
from __future__ import annotations

import argparse
import math
import os
import random
from typing import List, Tuple

import cv2
import numpy as np

W, H = 1280, 720
FPS = 25


def _road(frame: np.ndarray, horizon: int, asphalt: Tuple[int, int, int]) -> None:
    """Perspective road with kerbs, lane markings and grain."""
    h, w = frame.shape[:2]
    frame[:horizon] = (asphalt[0] // 3, asphalt[1] // 3, asphalt[2] // 3)
    for y in range(horizon, h):
        t = (y - horizon) / max(1, h - horizon)
        half = int(w * (0.06 + 0.62 * t))
        cx = w // 2
        cv2.line(frame, (cx - half, y), (cx + half, y),
                 tuple(int(c + 12 * t) for c in asphalt), 1)
        cv2.line(frame, (cx - half, y), (cx - half + 3, y), (90, 90, 95), 1)
        cv2.line(frame, (cx + half - 3, y), (cx + half, y), (90, 90, 95), 1)
    rng = np.random.default_rng(7)
    grain = rng.normal(0, 5.0, size=(h, w, 1)).astype(np.float32)
    frame[:] = np.clip(frame.astype(np.float32) + grain, 0, 255).astype(np.uint8)
    # dashed centre lines, converging with the road
    for i in range(14):
        t0, t1 = i / 14.0, (i + 0.55) / 14.0
        for t in (t0, t1):
            y0 = int(horizon + (h - horizon) * t)
            x0 = w // 2
            wid = max(2, int(1 + 14 * t))
            cv2.rectangle(frame, (x0 - wid // 2, y0), (x0 + wid // 2, y0 + int(4 + 26 * t)),
                          (215, 215, 215), -1)


def _shade(base, k):
    return tuple(max(0, min(255, int(c * k))) for c in base)


def _car(frame, cx, base_y, scale, colour, night=False, heading=1) -> None:
    """One vehicle, drawn with the parts a detector has to find separately."""
    bw = int(150 * scale)              # body width
    bh = int(78 * scale)               # body height
    rh = int(40 * scale)               # cabin height
    x1, x2 = cx - bw // 2, cx + bw // 2
    y1, y2 = base_y - bh, base_y
    # shadow: makes the contact edge unambiguous
    cv2.ellipse(frame, (cx, y2 + int(4 * scale)), (int(bw * 0.58), int(9 * scale)),
                0, 0, 360, (0, 0, 0), -1, cv2.LINE_AA)
    # body: vertical gradient (roof-lit, skirt-dark) reads as a painted surface
    pts = np.array([[x1, y2], [x1, y1 + int(bh * .28)], [x1 + int(bw * .12), y1],
                    [x2 - int(bw * .12), y1], [x2, y1 + int(bh * .28)], [x2, y2]], np.int32)
    grad = np.linspace(1.28, 0.72, bh, dtype=np.float32)
    for row in range(bh):
        col = _shade(colour, float(grad[row]))
        cv2.line(frame, (x1, y1 + row), (x2, y1 + row), col, 1)
    cv2.fillPoly(frame, [pts], _shade(colour, 0.95), cv2.LINE_AA)
    for row in range(bh):
        cv2.line(frame, (x1, y1 + row), (x2, y1 + row), _shade(colour, float(grad[row])), 1)
    cv2.polylines(frame, [pts], True, _shade(colour, 1.35), 1, cv2.LINE_AA)
    # cabin + glazing
    cab_x1, cab_x2 = x1 + int(bw * 0.22), x2 - int(bw * 0.22)
    cv2.rectangle(frame, (cab_x1, y1 - rh), (cab_x2, y1), (int(colour[0] * .8),) * 3, -1, cv2.LINE_AA)
    glass = (40, 60, 70) if not night else (18, 26, 34)
    cv2.rectangle(frame, (cab_x1 + int(4 * scale), y1 - rh + int(4 * scale)),
                  (cab_x2 - int(4 * scale), y1 - int(3 * scale)), glass, -1, cv2.LINE_AA)
    # wheels
    wr = max(2, int(13 * scale))
    for wx in (x1 + int(bw * 0.24), x2 - int(bw * 0.24)):
        cv2.circle(frame, (wx, y2 - int(wr * 0.35)), wr, (18, 18, 20), -1, cv2.LINE_AA)
        cv2.circle(frame, (wx, y2 - int(wr * 0.35)), max(1, wr // 2), (70, 70, 75), -1, cv2.LINE_AA)
    # lights and the plate rectangle
    lw, lh = max(2, int(16 * scale)), max(1, int(9 * scale))
    lit = (200, 230, 255) if night else (220, 220, 230)
    back = (60, 60, 220) if heading > 0 else (60, 60, 220)
    cv2.rectangle(frame, (x1 + int(5 * scale), y1 + int(bh * 0.45)),
                  (x1 + int(5 * scale) + lw, y1 + int(bh * 0.45) + lh), back, -1)
    cv2.rectangle(frame, (x2 - int(5 * scale) - lw, y1 + int(bh * 0.45)),
                  (x2 - int(5 * scale), y1 + int(bh * 0.45) + lh), lit, -1)
    pw, ph = max(4, int(40 * scale)), max(3, int(14 * scale))
    px, py = cx - pw // 2, y2 - int(ph * 1.6)
    cv2.rectangle(frame, (px, py), (px + pw, py + ph), (245, 245, 245), -1)
    if scale > 0.55:
        cv2.putText(frame, "GJ01AB1234", (px + 1, py + ph - 2), cv2.FONT_HERSHEY_SIMPLEX,
                    ph / 46.0, (20, 20, 20), max(1, int(1.4 * scale)), cv2.LINE_AA)


def _bus(frame, cx, base_y, scale, colour=(40, 120, 200)) -> None:
    bw, bh = int(300 * scale), int(120 * scale)
    x1, x2, y1, y2 = cx - bw // 2, cx + bw // 2, base_y - bh, base_y
    cv2.ellipse(frame, (cx, y2 + int(5 * scale)), (int(bw * .55), int(10 * scale)), 0, 0, 360,
                (0, 0, 0), -1, cv2.LINE_AA)
    cv2.rectangle(frame, (x1, y1), (x2, y2), colour, -1, cv2.LINE_AA)
    cv2.rectangle(frame, (x1, y1), (x2, y1 + int(10 * scale)), (250, 250, 250), -1)
    for i in range(6):
        wx = x1 + int(bw * (0.08 + 0.15 * i))
        cv2.rectangle(frame, (wx, y1 + int(22 * scale)),
                      (wx + int(bw * 0.11), y1 + int(52 * scale)), (45, 55, 62), -1)
    for wx in (x1 + int(bw * .2), x1 + int(bw * .8), x2 - int(bw * .2)):
        cv2.circle(frame, (wx, y2 - int(6 * scale)), max(2, int(15 * scale)), (18, 18, 20), -1)


def _bike(frame, cx, base_y, scale, colour=(60, 60, 60)) -> None:
    bw, bh = int(46 * scale), int(70 * scale)
    x1, x2, y1, y2 = cx - bw // 2, cx + bw // 2, base_y - bh, base_y
    cv2.ellipse(frame, (cx, y2 + int(3 * scale)), (int(bw * .6), int(6 * scale)), 0, 0, 360,
                (0, 0, 0), -1, cv2.LINE_AA)
    for wy in (y2 - int(9 * scale),):
        pass
    cv2.line(frame, (x1 + int(6 * scale), y2), (x2 - int(6 * scale), y2), (25, 25, 25),
             max(1, int(5 * scale)))
    for wx in (x1 + int(8 * scale), x2 - int(8 * scale)):
        cv2.circle(frame, (wx, y2 - int(8 * scale)), max(2, int(11 * scale)), (20, 20, 22), -1,
                   cv2.LINE_AA)
        cv2.circle(frame, (wx, y2 - int(8 * scale)), max(1, int(4 * scale)), (85, 85, 90), -1)
    cv2.rectangle(frame, (x1 + int(9 * scale), y1 + int(20 * scale)),
                  (x2 - int(9 * scale), y2 - int(18 * scale)), colour, -1, cv2.LINE_AA)
    cv2.circle(frame, (cx, y1 + int(13 * scale)), max(2, int(11 * scale)), (70, 90, 130), -1,
               cv2.LINE_AA)  # rider helmet


def _motorcycle_row(frame, y, n, scale, spread) -> None:
    for i in range(n):
        _bike(frame, int(W * 0.16 + i * spread), y, scale, (50 + 12 * (i % 4),) * 3)


def _kerb_parking(frame, horizon, h, w, t, palette, night=False) -> None:
    """Two rows of parked vehicles along the kerbs, small to large with depth.

    A police junction camera always has parked traffic at the edges, and a
    detector that only finds the cars in the middle of the road is exactly what
    the tight-box work is meant to fix - so the fixture has to contain them.
    """
    rng = random.Random(101)
    for side in (-1, 1):
        for i in range(9):
            depth = 0.06 + 0.9 * (i / 8.0)
            y = int(horizon + (h - horizon) * min(1.0, depth) + 4)
            half = int(w * (0.05 + 0.60 * depth))
            x = w // 2 + side * int(half * 0.86)
            scale = 0.14 + 0.72 * depth
            colour = palette[rng.randrange(len(palette))]
            if i % 4 == 3:
                _bike(frame, x, y, scale * 1.05, _shade(colour, 0.5))
            else:
                _car(frame, x, y, scale, colour, night=night, heading=side)


def _scene_junction_day(frame, t) -> None:
    horizon = int(H * 0.34)
    _road(frame, horizon, (74, 72, 70))
    palette = [(40, 40, 180), (200, 200, 210), (30, 120, 40), (150, 150, 30), (170, 170, 175),
               (25, 60, 120), (120, 40, 40), (230, 230, 235), (60, 60, 65)]
    # four moving lanes, ~9 vehicles each: real junction density
    for lane in range(4):
        for k in range(9):
            prog = (t * (0.34 + 0.06 * lane) + k * 0.111 + lane * 0.27) % 1.35
            scale = 0.16 + 0.98 * prog
            cx = int(W * (0.26 + 0.16 * lane) + (150 + 60 * lane) * prog * (1 if lane % 2 else -1))
            base_y = int(horizon + (H - horizon) * min(1.0, prog * 0.88) + 8)
            _car(frame, cx, base_y, scale, palette[(lane * 3 + k) % len(palette)],
                 heading=1 if lane % 2 else -1)
    _bus(frame, int(W * (0.62 - 0.16 * ((t * 0.3) % 1))), int(H * 0.80), 0.72)
    _motorcycle_row(frame, int(H * 0.92), 5, 0.92, 92)
    _kerb_parking(frame, horizon, H, W, t, palette)
    for x in (int(W * .08), int(W * .9)):
        cv2.rectangle(frame, (x, horizon - 130), (x + 70, horizon + 40), (58, 58, 62), -1)


def _scene_night_bridge(frame, t) -> None:
    horizon = int(H * 0.36)
    _road(frame, horizon, (26, 26, 30))
    palette = [(30, 30, 36), (34, 40, 60), (48, 46, 44), (26, 34, 30), (60, 58, 62)]
    for lane in range(3):
        for k in range(8):
            i = lane * 8 + k
            prog = (t * (0.3 + 0.05 * lane) + i * 0.041) % 1.3
            scale = 0.18 + 0.92 * prog
            cx = int(W * (0.26 + 0.2 * lane) + 120 * prog * (1 if lane % 2 else -1))
            base_y = int(horizon + (H - horizon) * min(1.0, prog * 0.92) + 6)
            _car(frame, cx, base_y, scale, palette[i % len(palette)], night=True)
            _kerb_parking(frame, horizon, H, W, t, palette, night=True)
        # headlight pool on the road
        if scale > 0.4:
            cv2.ellipse(frame, (cx, base_y + int(14 * scale)), (int(90 * scale), int(22 * scale)),
                        0, 0, 360, (70, 70, 55), -1)
    for x in (110, 420, 760, 1090):
        cv2.circle(frame, (x, int(H * 0.18)), 5, (200, 220, 255), -1)
        cv2.line(frame, (x, int(H * 0.18) + 5), (x, int(H * 0.18) + 26), (55, 55, 60), 3)


def _scene_parked_bikes(frame, t) -> None:
    frame[:] = (64, 66, 70)
    cv2.rectangle(frame, (0, 0), (W, int(H * 0.32)), (44, 46, 50), -1)
    y = int(H * 0.72)
    for i in range(13):
        _bike(frame, int(48 + i * 108 + 6 * math.sin(t * 0.6 + i)), y - (i % 3) * 12,
              0.86 + 0.03 * (i % 4), (45 + 18 * (i % 5), 45 + 18 * (i % 3), 50 + 18 * (i % 4)))
    cv2.line(frame, (0, y + 26), (W, y + 26), (150, 150, 150), 3)
    _car(frame, int(W * 0.88), int(H * 0.44), 0.34, (180, 180, 190))


def _scene_avenue_1080p(frame, t) -> None:
    h, w = frame.shape[:2]
    horizon = int(h * 0.33)
    _road(frame, horizon, (70, 68, 66))
    palette = [(30, 30, 150), (210, 210, 215), (35, 130, 45), (120, 40, 40), (200, 190, 60),
               (90, 90, 95), (240, 240, 245), (25, 90, 140)]
    for lane in range(5):
        for k in range(8):
            i = lane * 8 + k
            prog = (t * (0.32 + 0.05 * lane) + i * 0.047) % 1.42
            scale = (0.16 + 1.05 * prog) * (h / 720.0)
            cx = int(w * (0.2 + 0.14 * lane) + (240 + 40 * lane) * prog * (1 if lane % 2 else -1))
            base_y = int(horizon + (h - horizon) * min(1.0, prog * 0.86) + 8)
            _car(frame, cx, base_y, scale, palette[i % len(palette)])
    _kerb_parking(frame, horizon, h, w, t, palette)
    _bus(frame, int(w * (0.7 - 0.2 * ((t * 0.25) % 1))), int(h * 0.86), 0.95 * h / 720.0)
    _motorcycle_row(frame, int(h * 0.95), 5, 1.0 * h / 720.0, int(w * 0.13))


SCENES = {
    "junction_day": (_scene_junction_day, 0),
    "night_bridge": (_scene_night_bridge, 0),
    "dense_parked_bikes": (_scene_parked_bikes, 0),
    "avenue_1080p": (_scene_avenue_1080p, 1),   # 1920x1080
}


def build(name: str, out_dir: str, seconds: float, seed: int) -> str:
    fn, size_variant = SCENES[name]
    random.seed(seed)
    w, h = (W, H) if size_variant == 0 else (1920, 1080)
    path = os.path.join(out_dir, f"{name}.mp4")
    os.makedirs(out_dir, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, FPS, (w, h))
    if not writer.isOpened():
        raise SystemExit(f"cv2 could not open {path} for writing")
    frames = int(seconds * FPS)
    for i in range(frames):
        frame = np.zeros((h, w, 3), np.uint8)
        fn(frame, i / FPS)
        cv2.putText(frame, f"SYNTHETIC TEST FIXTURE - {name.replace('_', ' ').upper()}",
                    (16, h - 16), cv2.FONT_HERSHEY_SIMPLEX, h / 1400.0, (235, 235, 235), 1,
                    cv2.LINE_AA)
        writer.write(frame)
    writer.release()
    return path


# ----------------------------------------------------------------- derived mode
VARIANTS = {
    # name: (start_s, duration_s, speed, crop fraction of width, grade, out size)
    "junction_day": dict(start=2.0, seconds=8.0, speed=2.0, crop=None,
                         grade="day", size=(1280, 720),
                         caption="RECORDED TEST CLIP - real footage, 2x, not live"),
    "night_bridge": dict(start=6.0, seconds=8.0, speed=2.0, crop=None,
                         grade="night", size=(1280, 720),
                         caption="RECORDED TEST CLIP - night grade, exposure lowered"),
    "dense_parked_bikes": dict(start=10.0, seconds=8.0, speed=1.0, crop=(0.02, 0.30, 0.98, 0.96),
                               grade="day", size=(1280, 720),
                               caption="RECORDED TEST CLIP - cropped vehicle rows"),
    "avenue_1080p": dict(start=14.0, seconds=8.0, speed=2.0, crop=None,
                         grade="day", size=(1920, 1080),
                         caption="RECORDED TEST CLIP - 1080p re-scale"),
}


def _grade(frame, kind):
    if kind != "night":
        # mild contrast so plate-sized detail survives JPEG in the MJPEG path
        out = cv2.convertScaleAbs(frame, alpha=1.06, beta=-4)
        return out
    dark = cv2.convertScaleAbs(frame, alpha=0.42, beta=-6)
    blue = dark.astype(np.float32) * np.array([1.18, 1.06, 0.72], np.float32)
    out = np.clip(blue, 0, 255).astype(np.uint8)
    h, w = out.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx - w / 2) / w) ** 2 + ((yy - h / 2) / h) ** 2)
    vig = np.clip(1.25 - 1.15 * d, 0.25, 1.0)[..., None]
    return np.clip(out * vig, 0, 255).astype(np.uint8)


def build_from_source(name: str, source: str, out_dir: str, seed: int) -> str:
    """Re-time / crop / grade real footage into one labelled test clip."""
    spec = VARIANTS[name]
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise SystemExit(f"cannot read --source {source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out_w, out_h = spec["size"]
    path = os.path.join(out_dir, f"{name}.mp4")
    os.makedirs(out_dir, exist_ok=True)
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (out_w, out_h))
    if not writer.isOpened():
        raise SystemExit(f"cv2 could not open {path} for writing")
    start = int(min(spec["start"], max(0.0, total / fps - spec["seconds"] - 0.2)) * fps)
    frames_wanted = int(spec["seconds"] * FPS)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    written, i = 0, 0
    rng = np.random.default_rng(seed)
    while written < frames_wanted:
        grab_every = max(1.0, float(spec["speed"]) * fps / FPS)
        want = int(round(i * grab_every))
        if want > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(start + want, max(0, total - 1)))
        ok, frame = cap.read()
        i += 1
        if not ok or frame is None:
            break
        if spec["crop"]:
            cx1, cy1, cx2, cy2 = spec["crop"]
            frame = frame[int(cy1 * src_h):int(cy2 * src_h), int(cx1 * src_w):int(cx2 * src_w)]
        frame = _grade(frame, spec["grade"])
        frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
        # a whisper of encoder noise: a clean synthetic gradient compresses to
        # almost nothing and hides banding artefacts that a real stream has
        noise = rng.normal(0, 1.6, size=frame.shape).astype(np.float32)
        frame = np.clip(frame.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        # TOP-RIGHT: the runtime OSD owns the bottom-right corner, and footage
        # stamped by an earlier tool may already carry text bottom-left, so a
        # fixture caption printed over either reads as a broken display.
        font, sc = cv2.FONT_HERSHEY_SIMPLEX, out_h / 1500.0
        (tw, th), bl = cv2.getTextSize(spec["caption"], font, sc, 1)
        cv2.putText(frame, spec["caption"], (out_w - tw - 16, 30), font, sc,
                    (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, spec["caption"], (out_w - tw - 16, 30), font, sc,
                    (235, 245, 235), 1, cv2.LINE_AA)
        writer.write(frame)
        written += 1
    cap.release()
    writer.release()
    if not written:
        raise SystemExit(f"no frames written for {name} from {source}")
    return path


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--scene", action="append", default=[])
    ap.add_argument("--source", default=None,
                    help="real footage to re-time/grade; omit for --mode synthetic")
    ap.add_argument("--mode", choices=["derived", "synthetic"], default=None)
    args = ap.parse_args(argv)
    names = args.scene or list(SCENES)
    mode = args.mode or ("derived" if args.source else "synthetic")
    if mode == "derived" and not args.source:
        raise SystemExit("--mode derived needs --source")
    for n in names:
        p = (build_from_source(n, args.source, args.out_dir, args.seed) if mode == "derived"
             else build(n, args.out_dir, args.seconds, args.seed))
        cap = cv2.VideoCapture(p)
        print(f"[{mode:9s}] {os.path.basename(p):26s} {cap.get(cv2.CAP_PROP_FRAME_COUNT):5.0f} frames "
              f"{int(cap.get(3))}x{int(cap.get(4))} {os.path.getsize(p) / 1e6:5.2f} MB")
        cap.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
