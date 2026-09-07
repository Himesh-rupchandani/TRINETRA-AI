# TRINETRA — vehicle + plate training for THIS footage

Not a generic YOLO tutorial. Every number below comes from the existing
TRINETRA pipeline plus the reference clip
[`VID20260907113848.mp4`](https://drive.google.com/file/d/1PQZz_WTHp9OOvepr86E9iihFBpej3TYF/view?usp=drivesdk)
(184 MB, recorded 2026-09-07 11:38 local — late morning) and the in-repo
Gujarat CCTV stills at `trinetra-ai/public/cctv/` (1376×768 elevated-pole
views of the same domain: autos, bikes, cars, buses, trucks, day/night/rain).

```
Uploaded Traffic Video
        ↓
OpenCV
        ↓
Fine-tuned YOLO11s  (car / motorcycle / bus / truck / autorickshaw)
        ↓
Vehicle bounding boxes
        ↓
ByteTrack-style tracker  (unchanged)
        ↓
Plate YOLO11n  →  morphology fallback  →  heuristic lower-half crop
        ↓
RapidOCR / EasyOCR     (reject < 0.60 → Unknown, never invent)
        ↓
normalize_plate()      (GJ 01 AB-1234 → GJ01AB1234)
        ↓
VehicleEvent.plate_number  =  cross-camera identity
        ↓
CAM1 → CAM2 → CAM4     (existing /api/v1/vehicles/{plate}/route)
```

The dashboard, sidebar, navbar, Live Camera, Profile, Vehicle Log, Map,
search, routes, colours and components are **not** touched.

---

## 1. What model the project currently uses

| Knob | cv-engine | backend live view |
|---|---|---|
| Architecture | **Ultralytics YOLO11** | same |
| Size | **yolo11s.pt** (COCO) | `YOLO_MODEL_PATH=models/yolo11s.pt` |
| Classes requested | COCO 2/3/5/7 → car, motorcycle, bus, truck | same |
| Input | `INFERENCE_IMGSZ=640` | `DETECTION_IMGSZ=640` |
| Confidence | `CONF_THRESHOLD=0.35` | `CONFIDENCE_THRESHOLD=0.45` |
| NMS IoU | Ultralytics default **0.70** (now 0.50) | same (now `DETECTION_IOU=0.50`) |
| Tracking | ByteTrack-style Kalman + IoU (`track_iou=0.25`) | `SimpleTracker` IoU 0.25 |
| Plate detector | **none** — lower-half vehicle crop | same |
| OCR | EasyOCR / RapidOCR | RapidOCR then EasyOCR |
| Plate reject | 0.60 (Unknown, never invented) | `OCR_MIN_CONFIDENCE=0.60` |

There is no Haar cascade in the live path. There is no dedicated plate
model. ANPR is “crop the vehicle → OCR”.

---

## 2. Fine-tune or train new?

**Fine-tune the existing YOLO11s. Do not train from scratch.**

~80–180 frames from a single 184 MB clip is domain adaptation, not a
new detector. The COCO backbone already knows cars/bikes/buses/trucks;
what it lacks is *this* elevated CCTV angle, *this* Indian vehicle mix
(auto-rickshaws), and *this* small-object scale.

Train a **new 1-class YOLO11n plate detector**. Vehicle boxes are not
plates; OCR on a 200×200 auto crop is why plates come back Unknown today.

Do **not** retrain the tracker. Box jitter and ID switches on this
footage are mostly missed detections, not association.

Keep RapidOCR. Do not train an OCR model.

---

## 3. Recommended architecture

| Stage | Model | Why |
|---|---|---|
| Vehicles | **YOLO11s**, fine-tuned, 5 classes, imgsz **960** | s not n (need small-bike recall); s not m (hackathon CPU). 960 because 640 collapses far motorcycles on 1376-px CCTV. |
| Plates | **YOLO11n**, 1 class `license_plate`, imgsz **640** on the *vehicle crop* | n is enough when the search area is already a vehicle. |
| OCR | existing RapidOCR / EasyOCR | no fake plates below 0.60 |
| Tracking | existing ByteTrack-style | unchanged |

---

## 4. Dataset structure

```
cv-engine/training/datasets/
  vehicles/
    images/{train,val,test}/*.jpg
    labels/{train,val,test}/*.txt     # YOLO cx cy w h, class 0-4
    data.yaml
  plates/
    images/{train,val,test}/*.jpg     # same frames
    labels/{train,val,test}/*.txt     # class 0 = license_plate
    data.yaml
cv-engine/models/
  original/yolo11s.pt                 # backup, never overwritten
  trained/vehicles/best.pt
  trained/plates/best.pt
```

---

## 5. Required vehicle classes

From the Gujarat stills (and any Ahmedabad street at 11:38 in September):

| class | why |
|---|---|
| `car` | sedans / SUVs, nearest Swift-sized objects |
| `motorcycle` | densest class; many < 40 px tall |
| `bus` | AMTS / BRTS in rain/night stills |
| `truck` | delivery / mini-trucks |
| `autorickshaw` | **dominant in this city, absent from COCO** |

Do not add `person`. Do not add `bicycle` unless a scene actually needs it
(`include_bicycles=True` already exists). Map `van` → `truck`.

**Annotate** a tight axis-aligned box around the full visible vehicle,
including partially-cut vehicles at the frame edge. Do **not** box
pedestrians, shopfronts, or traffic lights. One box per vehicle, even
when they overlap.

---

## 6. Number plate annotation

A **separate** box around the plate only, class `license_plate`.

```
Vehicle box  →  Plate box  →  OCR  →  GJ01AB1234
```

Skip plates that are unreadable (motion blur, < ~16 px wide, steep
angle). Those vehicles still get a vehicle box; ANPR must return
**Unknown**, not a guess.

Front and rear plates both count. Motorcycle tail plates are tiny —
annotate only when characters are actually separable.

---

## 7. How many frames to extract

For `VID20260907113848.mp4` (184 MB, likely 2–4 min of 1080p/720p):

* Interval **1.0 s** (1.5 s if duration > 3 min)
* Drop duplicates with 32×18 grayscale correlation ≥ 0.985
* Target **80–180 frames**, cap 200

Not every frame. A 30 fps clip would otherwise produce thousands of
near-identical labels and leak into the test split.

---

## 8. How to annotate

```
python training/prepare_all.py --video feeds/reference_traffic.mp4
```

That auto-labels with stock YOLO11s @ 1280 px (so small vehicles are not
missed at label time) plus an autorickshaw colour heuristic and
morphology plate proposals.

**Then open the labels in CVAT / Label Studio / LabelImg and correct
them.** Auto-labels are a starting point. In particular:

* re-tag autos that COCO called `car`
* delete phantom boxes on shop signs
* delete plate proposals that are headlights / yellow auto roofs
* add missed far motorcycles

---

## 9. Train / val / test split

**By time, never by random frames.**

| split | timeline | purpose |
|---|---|---|
| train | first 70% | fine-tune |
| val | 70–85% | early stopping |
| test | last 15% | held-out seconds of the *same camera*, not the same vehicles 0.04 s later |

`extract_frames.py` does this. Do not `sklearn.train_test_split` the
JPEGs.

---

## 10. Augmentation (matched to this CCTV)

Vehicles:

| aug | value | why |
|---|---|---|
| hsv_v | 0.40 | day / dusk / night / rain stills |
| hsv_s | 0.50 | |
| degrees | **5** | fixed pole, not a handheld selfie |
| scale | 0.60 | small far vehicles |
| mosaic | 1.0 | small-object | 
| fliplr | 0.5 | vehicles have no text direction |
| flipud | 0 | CCTV is never upside down |
| erasing | 0.15 | occlusion by other vehicles |
| shear / big perspective | off | would look unlike a pole camera |

Plates: **fliplr = 0** (reverses `GJ01AB1234`), mosaic 0.5, no
perspective warp (destroys characters).

---

## 11. Training configuration

| | vehicles | plates |
|---|---|---|
| model | yolo11s (pretrained) | yolo11n (pretrained) |
| imgsz | **960** | 640 (on vehicle crop) |
| epochs | 80, patience 20 | 80, patience 20 |
| batch | 8 (GPU) / 2 (CPU) | 16 / 4 |
| optimizer | AdamW | AdamW |
| lr0 | 0.001 | 0.001 |
| freeze | 10 (backbone) | 0 |
| conf at infer | 0.30 | 0.25 |
| NMS IoU | 0.50 | 0.50 |
| GPU | 1× 8 GB is plenty | same |

960 px is required because the stills are 1376×768 with motorcycles that
are ~20–40 px tall. 640 px training would see them as 9–18 px.

---

## 12. Exact training command

```bash
cd cv-engine
python training/prepare_all.py --video feeds/reference_traffic.mp4
# review training/datasets/vehicles/labels/**  then:
python training/train_vehicles.py \
  --model models/original/yolo11s.pt \
  --data  training/datasets/vehicles/data.yaml \
  --imgsz 960 --epochs 80 --batch 8 --device 0 --patience 20 --lr0 0.001 --freeze 10

python training/train_plates.py \
  --model yolo11n.pt \
  --data  training/datasets/plates/data.yaml \
  --imgsz 640 --epochs 80 --batch 16 --device 0 --patience 20 --lr0 0.001
```

CPU fallback: `--device cpu --batch 2 --workers 0 --imgsz 640` (slower,
weaker on far bikes).

Equivalent Ultralytics CLI:

```bash
yolo detect train model=models/original/yolo11s.pt \
  data=training/datasets/vehicles/data.yaml \
  imgsz=960 epochs=80 batch=8 device=0 optimizer=AdamW lr0=0.001 \
  patience=20 freeze=10 fliplr=0.5 flipud=0 degrees=5 mosaic=1.0
```

---

## 13. Exact validation command

```bash
python training/evaluate.py --weights models/trained/vehicles/best.pt --split val --imgsz 960
python training/evaluate.py --weights models/trained/vehicles/best.pt --split test --imgsz 960
python training/evaluate.py --weights models/trained/plates/best.pt \
  --data training/datasets/plates/data.yaml --split val --imgsz 640
```

```bash
yolo detect val model=models/trained/vehicles/best.pt \
  data=training/datasets/vehicles/data.yaml split=test imgsz=960
```

---

## 14. Exact inference / test command

```bash
python training/infer_video.py \
  --video feeds/reference_traffic.mp4 \
  --weights models/trained/vehicles/best.pt \
  --plate-weights models/trained/plates/best.pt \
  --imgsz 960 --conf 0.30 --iou 0.50 \
  --out training/runs/infer_reference.mp4
```

```bash
python training/compare_models.py \
  --original models/original/yolo11s.pt \
  --trained  models/trained/vehicles/best.pt \
  --video    feeds/reference_traffic.mp4 --imgsz 960 --conf 0.30
```

Production (no UI change): drop `best.pt` in
`models/trained/vehicles/` and restart cv-engine / backend. `MODEL_PATH`
already resolves there.

---

## 15. Where the trained model is saved

```
cv-engine/models/original/yolo11s.pt          # stock backup
cv-engine/models/trained/vehicles/best.pt     # used automatically
cv-engine/models/trained/plates/best.pt
cv-engine/training/runs/vehicles/weights/best.pt
cv-engine/training/runs/plates/weights/best.pt
TRINETRAAI/backend/models/trained/vehicles/best.pt   # optional copy
```

The original file is copied once by `backup_original()` / `fetch_models.py`
and is never overwritten.

---

## 16. How it is integrated with OpenCV

No rewrite of the OpenCV application.

* `VehicleDetector` and `VehicleDetectionService` resolve
  `models/trained/vehicles/best.pt` when present, filter by
  `model.names` (COCO ids *or* the 5-class head), NMS IoU 0.50.
* `anpr/plate_detector.py` and `backend/app/services/plate_detector.py`
  run plate YOLO → morphology → legacy lower-half crop, then OCR.
* Uploaded videos (`uploaded_video_service`) infer at
  `UPLOAD_DETECTION_IMGSZ=960` so far vehicles survive.
* Live MJPEG still draws the same green boxes. No dashboard change.
* Cross-camera identity is still `normalize_plate()` on
  `VehicleEvent.plate_number` — `GET /api/v1/vehicles/{plate}/route`
  already returns CAM1 → CAM2 → CAM4.

---

## 17. How to test on the provided traffic video

1. `python training/download_reference.py` (or copy the Drive file to
   `cv-engine/feeds/reference_traffic.mp4`).
2. `python training/analyze_video.py --video feeds/reference_traffic.mp4`
3. Train as in §12.
4. `python training/infer_video.py --video feeds/reference_traffic.mp4`
5. Upload the same file in the existing Live Camera **Upload** dialog as
   `CAM1`, then again as `CAM2` / `CAM4` on other clips. Matching plates
   become one vehicle path. Unreadable plates stay `Unknown`.

---

## 18. How to measure improvement over the existing model

* `compare_models.py` — boxes/frame and small-box rate on identical
  sampled frames (original vs trained).
* `evaluate.py --split test` — precision / recall / mAP50 / mAP50-95 on
  the **time-held-out** 15%.
* Visual: `infer_reference.mp4` vs the stock model on the same clip.
  Count missed obvious vehicles, duplicate boxes, jumps, road false
  positives.
* ANPR: `scripts/validate_anpr.py --images <dir> --truth truth.json`
  reports vehicle-detected / plate-read / Indian-format **separately**.
  Do not merge them into one fake accuracy.
* mAP on auto-labels is self-agreement. Trust the held-out seconds and
  the visual pass.

---

## 19. Limitations caused by the video quality

* **Far plates are below OCR resolution** (often < 16 px). The correct
  output is Unknown, not a hallucinated `GJ…` string.
* **Auto-rickshaws** fool COCO. Until the 5-class model is trained and
  reviewed they will still be `car` or missed.
* **Night rain / headlight bloom / motion trails** (see cctv-04, cctv-06)
  destroy plate contrast. Brightness augs help detection more than OCR.
* **Dense overlap** in market streets — NMS 0.50 is a compromise; 0.70
  was merging neighbouring bikes.
* **184 MB phone-named clip** (`VIDYYYYMMDDHHMMSS`) may be a handheld
  recording of a street or of a CCTV monitor. If it is handheld, the 5°
  rotation cap is still safe; if it is a screen recording, extra
  moiré/compression will hurt OCR further.
* This sandbox cannot TLS to Google Drive or GitHub release assets, so
  the 184 MB binary and `yolo11s.pt` must be fetched on a normal machine
  (`gdown` / `scripts/fetch_models.py`). The training code is written to
  run there.

---

## 20. Files created or modified

**Created**

* `cv-engine/training/` — analyze, extract, auto-label, train, eval, infer, compare
* `cv-engine/detection/model_paths.py`
* `cv-engine/models/{original,trained/...}/`
* `TRINETRAAI/backend/app/services/plate_detector.py`
* `TRINETRAAI/backend/models/{original,trained/...}/`
* tests: `test_vehicle_classes.py`, `test_plate_detector.py`,
  `test_model_paths.py`, `test_trained_model_paths.py`

**Modified (pipeline only, no UI)**

* `cv-engine/detection/vehicle_detector.py` — trained-weight resolve, custom classes, NMS IoU
* `cv-engine/detection/classes.py` — `autorickshaw` + aliases
* `cv-engine/anpr/plate_detector.py` — YOLO plate + morphology + heuristic
* `cv-engine/config/settings.py` — `iou_threshold`, `plate_model_path`, `prefer_trained_model`
* `cv-engine/pipeline/camera_pipeline.py` — plate crops, skip tiny OCR
* `TRINETRAAI/backend/app/core/config.py` — `PREFER_TRAINED_MODEL`, `DETECTION_IOU`, `UPLOAD_DETECTION_IMGSZ`, `PLATE_MODEL_PATH`
* `TRINETRAAI/backend/app/services/vehicle_detection_service.py`
* `TRINETRAAI/backend/app/services/ocr_service.py`
* `TRINETRAAI/backend/app/services/uploaded_video_service.py` — `timedelta` import (was crashing finalize), 960-px upload infer

Unrelated dashboard / navbar / map / profile files were not edited.
