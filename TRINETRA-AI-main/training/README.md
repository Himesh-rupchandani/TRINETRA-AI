# TRINETRA AI — footage analysis & model-training toolkit

Scripts for PARTS 2–7 of the multi-video brief: look at the *actual* footage,
decide which component is weak, build a leakage-free dataset from that footage,
fine-tune **only** the weak component, and measure baseline vs fine-tuned.

Nothing here invents data. Every script prints what it measured, and prints
`n/a` for anything it could not measure.

Run everything from the repository root with the project virtualenv:

```bash
.venv/bin/python training/<script>.py --help
```

---

## PART 2 — look at the footage first

```bash
.venv/bin/python training/analyze_video.py --video footage/junction.mp4
```

Reports resolution, fps, codec, lighting (incl. night/IR detection), sharpness
(motion-blur risk), traffic density, vehicle classes actually present, vehicle
and **estimated plate pixel height**, occlusion, camera geometry — then
recommends what to do. Writes `training/reports/<stem>_footage.json`.

Read the `plate size est.` line first. If the median plate height is below
~16 px, no detector or OCR engine on earth will read those plates: the answer is
a higher-resolution or closer camera, not more training.

## PART 3 — decide what is weak

The written assessment for this project is in
[`docs/MULTI_VIDEO_ASSESSMENT.md`](../docs/MULTI_VIDEO_ASSESSMENT.md).
Summary of the decision it reaches:

| Component | Verdict | Why |
|---|---|---|
| Vehicle detector (YOLO11s, COCO) | **keep** | already detects car/motorcycle/bus/truck; only thresholds were tuned |
| Plate localisation | **train this** | the stage did not exist; a classical OpenCV proposer now stands in for it |
| OCR (RapidOCR) | **do not retrain** | a general recogniser is accurate on a good crop; its errors come from the crop |

Re-run PART 2 on your own footage before accepting this — if your vehicle
recall is below ~0.8, the vehicle detector becomes the weak component instead.

## PART 4 — build a dataset from the real video

```bash
# 1. representative frames, split by TIME SEGMENT (no leakage)
.venv/bin/python training/extract_frames.py \
    --video footage/junction.mp4 --video footage/highway.mp4 \
    --out training/dataset --stride 10 --max-frames 400

# 2. machine-proposed plate boxes — REVIEW THEM before training
.venv/bin/python training/autolabel_plates.py --dataset training/dataset

# 3. validate + emit the Ultralytics data yaml
.venv/bin/python training/build_dataset.py --dataset training/dataset
```

* `extract_frames.py` drops near-duplicate frames and assigns whole contiguous
  time segments to train / val / test, so one vehicle's pass through the scene
  can never appear in two splits.
* `autolabel_plates.py` writes YOLO labels **and** `autolabel_report.json`
  listing every proposal with its OCR text and confidence. Fix them in LabelImg
  / CVAT / Roboflow — start with the entries flagged `needs_review`.
* `build_dataset.py` fails loudly on missing labels, out-of-range boxes, empty
  val/test splits and any segment that leaked across splits.

## PART 5 — fine-tune only the weak component

```bash
.venv/bin/python training/train_plate_detector.py \
    --data training/dataset/plates.yaml --dry-run     # show the plan
.venv/bin/python training/train_plate_detector.py \
    --data training/dataset/plates.yaml
```

* Defaults are auto-sized to the machine: on a CPU box, `imgsz 416`,
  `batch 4`, 40 epochs, `amp=False`; on a GPU, `imgsz 640`, `batch 16`.
* The starting weights are copied to `TRINETRAAI/backend/models/baseline/`
  and are **never** written to.
* The result is saved as a **new** file,
  `TRINETRAAI/backend/models/plate_detector.pt`, next to a `.json` recording
  the exact run. An existing fine-tuned model is renamed with a timestamp, not
  overwritten.
* The backend picks the new file up automatically (`PLATE_MODEL_PATH`); delete
  or rename it to fall straight back to the classical proposer.
* Augmentation matches the problems PART 2 finds in CCTV footage — blur,
  small/far plates, lighting — and never flips (plates are not mirrored).

## PART 6/7 — measure it

```bash
.venv/bin/python training/evaluate.py \
    --data training/dataset/plates.yaml \
    --plate-model TRINETRAAI/backend/models/plate_detector.pt \
    --ocr-truth training/ocr_truth.csv
```

Produces, on the **held-out test split**:

* plate detection — precision / recall / F1 / TP / FP / FN for the classical
  proposer *and* the fine-tuned model, plus mAP50 and mAP50-95 from Ultralytics;
* a separate breakdown for small plates (`< 16 px` tall — the far vehicles);
* OCR — exact-match rate, character error rate, wrong reads, and how many reads
  the confidence policy refused (a refusal becomes *Unknown* in the UI, which is
  the safe outcome; only `wrong_reads` can mislead an investigator).

`--ocr-truth` is a CSV with columns `image,plate`, paths relative to the CSV.

Ship the fine-tuned model only if it beats the baseline on the test split.
Keep both reports — `training/reports/` is the audit trail.

---

## `tools/make_demo_clips.py` — synthetic fixtures, clearly labelled

```bash
.venv/bin/python training/tools/make_demo_clips.py \
    --source sample.mp4 --out-dir /tmp/demo_clips \
    --clip CAM1:GJ01AB1234 --clip CAM2:MH12XY4567 --clip CAM3:GJ01AB1234
```

Composites a rendered number plate onto real detected vehicles so the
multi-video matching path can be exercised when no footage with legible plates
is available. **Its output is a test fixture, not evidence, and its accuracy
says nothing about real-world performance.** Never analyse these clips into the
production database.
