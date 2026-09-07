# Footage analysis — TRINETRA vehicle + plate training

This is the source of truth for the training configuration.

## Reference clip (Google Drive)

| | |
|---|---|
| File id | `1PQZz_WTHp9OOvepr86E9iihFBpej3TYF` |
| Listing name | `VID20260907113848.mp4` |
| Listed size | **184 MB** (too large for Drive's virus scan) |
| Timestamp in name | **2026-09-07 11:38:48** — late morning, daylight |
| Naming | Android `VIDYYYYMMDDHHMMSS` (phone recording of a street, or of a CCTV monitor) |
| URL | https://drive.google.com/file/d/1PQZz_WTHp9OOvepr86E9iihFBpej3TYF/view?usp=drivesdk |
| Local path | `cv-engine/feeds/reference_traffic.mp4` |

This environment can *see* the Drive listing (filename + 184 MB) but cannot
complete a TLS handshake to `drive.google.com`, so the binary was not
decoded here. `python training/download_reference.py` / `analyze_video.py`
re-fills the numeric table (resolution, FPS, duration, blur, motion) as
soon as the file is on disk (`training/reports/FOOTAGE_DECODED.md`).

A 184 MB late-morning clip is typically 2–4 minutes of 1080p30 or longer
720p. Treat duration as “a few minutes of continuous traffic”, not a
24-hour DVR dump — which is why we sample at 1 Hz, not every frame.

## Domain stills actually decoded here

`trinetra-ai/public/cctv/*.jpg` — the project's own Gujarat urban camera
views, all **1376×768**. These are the same elevated-pole, mixed-traffic
distribution Sentinel Ahmedabad cameras produce, and they are what the
training knobs were set from.

| file | lighting (mean luma) | what is in the frame | plates |
|---|---|---|---|
| cctv-01 | day, 112.5 | intersection, 30+ vehicles, autos + bikes + cars overlapping, pedestrians | nearest white Swift plate ~40–80 px wide, readable; far vehicles not |
| cctv-02 | day, 99.9 | dense market street, autos dominate, heavy occlusion | essentially unreadable |
| cctv-03 | dusk, 64.7 | aerial river bridge, hundreds of tiny vehicles | impossible (few pixels) |
| cctv-04 | night, 69.1 | arterial, motion trails, headlight bloom | nearest car maybe 20–30 px; trails kill OCR |
| cctv-05 | day, 100.9 | boulevard, truck + bikes, park pedestrians | truck GJ plate ~30–40 px |
| cctv-06 | night rain, 66.3 | wet road reflections, bus 413, autos | washed out |

Evidence close-ups (`public/evidence/veh-car.jpg`) show a **front-facing**
Indian plate `GJ01AB1234` filling ~80–100 px of a 1376-px frame — that is
the *best case* ANPR will ever see. The live cameras are the stills above,
not that hero crop.

## Camera geometry (from the stills)

- **Angle:** elevated pole / overpass, 20–40° down, looking along the road.
- **Distance:** near vehicles 4–12 m (large boxes); far vehicles 40–80 m
  (a few percent of the frame, often < 30 px tall).
- **Vehicles per frame:** 8–40 in city stills; 100+ on the bridge.
- **Motion:** moving in all stills except parked edge bikes. Night still
  has light trails → shutter too slow for plates.
- **Quality:** compressed JPEG CCTV, not cinema. Rain + night is noisy.
- **Occlusion / overlap:** constant. Autos hide bikes; buses hide cars.
- **Front and rear plates** both appear (oncoming + receding). Motorcycle
  tail plates are tiny.

## What will make the *current* YOLO11s @ 640 miss vehicles

1. **Auto-rickshaws** — not a COCO class. Often `car` or dropped.
2. **Far motorcycles** — 640-px inference on a 1376-px frame shrinks a
   24-px bike to ~11 px.
3. **NMS 0.70** — merges neighbouring bikes/autos in cctv-01/02.
4. **Conf 0.45 on the live view** — already aggressive for small boxes
   (cv-engine's 0.35 is healthier).
5. **Night bloom + rain reflections** — false negatives, not false
   plates (OCR already refuses them).
6. **Partial vehicles** at the frame edge.

## Number-plate pixel budget

| range | plate width | OCR |
|---|---|---|
| near (cctv-01 Swift, evidence car) | 40–100 px | possible |
| mid | 16–40 px | low-confidence / Unknown |
| far / aerial / rain | < 16 px | **Unknown**. Do not invent. |

Camera angle is *not* the main plate problem for near vehicles (they are
almost front/rear-on). Distance and compression are.

## Training implications (locked)

- Fine-tune YOLO11s, 5 classes including `autorickshaw`, **imgsz 960**.
- Separate plate YOLO11n + morphology fallback + existing OCR.
- NMS IoU **0.50**, infer conf **0.30** for the trained model.
- Time-based split, 1 Hz sampling, 80–180 frames from this clip.
- Vehicle augs: brightness, mosaic, scale, 5° roll, horizontal flip.
- Plate augs: **no horizontal flip**.
- Tracker stays. UI stays.
