# Model Weights Directory

Place your pre-trained computer vision model weights in this directory:

- `yolo11n.pt` / `yolo11s.pt` / `yolo11m.pt`: YOLO11 Ultralytics object detection weights
- OCR weights or license plate detection models

When weights are not present, TRINETRA AI automatically falls back to its built-in Mock / Demo Mode or standard lightweight Haar/DNN detectors.

## Live-view vehicle detection

`yolo11s.pt` in this directory powers the real-time green vehicle boxes on the
live camera view (`GET /api/cameras/{id}/live/detect`). Put the official
Ultralytics `yolo11s.pt` here (`YOLO_MODEL_PATH=models/yolo11s.pt`). If it is
missing, the in-repo `trinetra_detection/models/yolo11n.pt` (official COCO
weight, shipped with the standalone detection module) is used so detection
works offline; if that is also absent, Ultralytics downloads the configured
weight on first use. Without any weights the live view keeps working — just
without boxes.

## Multi-video analysis (`/api/analysis/*`)

Two model slots are used by the offline multi-video pipeline:

| File | Setting | Purpose | If missing |
|---|---|---|---|
| `yolo11s.pt` | `YOLO_MODEL_PATH` | vehicle detection (car / motorcycle / bus / truck) | analysis fails with a clear message; live view still works |
| `plate_detector.pt` | `PLATE_MODEL_PATH` | number-plate localisation inside a vehicle box | falls back to the classical OpenCV plate proposer — slightly lower precision, never a crash |

### Weight-safety policy

* `baseline/` holds untouched copies of the **original** weights. Nothing in
  this project ever writes to them.
* Fine-tuned models are written as **new files** (`plate_detector.pt`, plus a
  `.json` with the exact training run). An existing fine-tuned file is renamed
  with a timestamp rather than overwritten.
* To roll back to the shipped behaviour, delete or rename `plate_detector.pt`
  and restart the backend.

`*.pt` / `*.onnx` are git-ignored (including `baseline/`): weights are large
binaries and belong in release artefacts or object storage, not in the repo.
Train a plate detector with `training/train_plate_detector.py`.
