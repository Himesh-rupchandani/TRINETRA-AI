# Model Weights Directory

Place your pre-trained computer vision model weights in this directory:

- `yolo11n.pt` / `yolo11s.pt` / `yolo11m.pt`: YOLO11 Ultralytics object detection weights
- OCR weights or license plate detection models

When weights are not present, TRINETRA AI automatically falls back to its built-in Mock / Demo Mode or standard lightweight Haar/DNN detectors.

## Live-view vehicle detection

`yolo11s.pt` in this directory powers the real-time green vehicle boxes on the
live camera view (`GET /api/cameras/{id}/live/detect`). Put the official
Ultralytics `yolo11s.pt` here (`YOLO_MODEL_PATH=models/yolo11s.pt`); if it is
missing, Ultralytics downloads it on first use. Without weights the live view
keeps working — just without boxes.
