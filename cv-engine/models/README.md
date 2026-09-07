# Model weights

```
models/
  original/yolo11s.pt          # stock COCO YOLO11s — NEVER overwritten
  trained/vehicles/best.pt     # fine-tuned on the Gujarat CCTV / Drive clip
  trained/plates/best.pt       # 1-class number-plate detector
```

`VehicleDetector` prefers `trained/vehicles/best.pt` when it exists, then
falls back to `original/yolo11s.pt`, then a bare `yolo11s.pt` (Ultralytics
download). Set `PREFER_TRAINED_MODEL=false` or `MODEL_PATH=` to an explicit
file to force the original for A/B tests.

Fetch the stock weights once (on a network that can reach GitHub releases):

```
python scripts/fetch_models.py --yolo yolo11s.pt --skip-ocr
```

`.pt` files are gitignored.
