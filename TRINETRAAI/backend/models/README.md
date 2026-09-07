# Model Weights Directory

```
models/
  original/yolo11s.pt          # stock COCO YOLO11s — never overwritten
  trained/vehicles/best.pt     # fine-tuned Gujarat CCTV vehicle detector
  trained/plates/best.pt       # 1-class number-plate detector
  yolo11s.pt                   # optional stock copy (legacy path)
```

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

When `models/trained/vehicles/best.pt` exists and `PREFER_TRAINED_MODEL=true`
(the default), the live view and the uploaded-video pipeline load the
fine-tuned weights instead. The original file is left untouched so you can
A/B test with `PREFER_TRAINED_MODEL=false`.
