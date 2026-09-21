# TRINETRA AI — Pre-implementation Assessment (Multi-Video Vehicle Tracking)

> Produced by inspecting the actual repository before any code was written.
> Nothing below is assumed — every line is traceable to a file in this repo.

## 1. What is actually in the project

| Area | Actual implementation | Evidence |
|---|---|---|
| Frontend framework | **React 19 + TypeScript + Vite 8 + TailwindCSS 3 + react-router-dom 7** (no Next.js) | `trinetra-ai/package.json`, `trinetra-ai/vite.config.ts` |
| Frontend design system | Hand-rolled Tailwind component layer (`.panel`, `.btn-*`, `.chip`, `.data-table`, `.plate`, `.input`) | `trinetra-ai/src/index.css` |
| Backend framework | **FastAPI + SQLAlchemy 2 + Pydantic v2 + Uvicorn** | `TRINETRAAI/backend/app/main.py` |
| Routers mounted | `/api` **and** `/api/v1` (both prefixes, same routers) | `app/main.py` bottom |
| Database / storage | **SQLite via SQLAlchemy** (`sqlite:///./trinetra.db`), auto-migrating with `ALTER TABLE ADD COLUMN` | `app/database/database.py::_auto_migrate` |
| Existing tables | `cameras`, `detections`, `vehicle_observations`, `watchlist`, `vehicle_events`, `alerts`, `officers` | `app/database/models.py` |
| OpenCV implementation | `cv2.VideoCapture` decode loop with N-frame sampling (`PROCESS_EVERY_N_FRAMES=3`), MJPEG live streaming | `app/services/uploaded_video_service.py`, `app/camera/manager.py` |
| **Vehicle detection model** | **Ultralytics YOLO11 (`yolo11s.pt`)**, COCO-pretrained, *not* fine-tuned. Loaded lazily and shared process-wide. | `app/services/vehicle_detection_service.py`, `cv-engine/detection/vehicle_detector.py` |
| Model weights | `TRINETRAAI/backend/models/yolo11s.pt` (`YOLO_MODEL_PATH`); **not present on disk** → Ultralytics auto-downloads | `app/core/config.py`, `backend/models/README.md` |
| Model input resolution | `DETECTION_IMGSZ = 640` (cv-engine: `INFERENCE_IMGSZ=640`) | `app/core/config.py` |
| Detection classes | COCO ids `{2: car, 3: motorcycle, 5: bus, 7: truck}` — passed as `classes=` so nothing else is even decoded | `vehicle_detection_service.VEHICLE_CLASS_IDS`, `cv-engine/detection/classes.py` |
| Confidence threshold | `CONFIDENCE_THRESHOLD = 0.45` (backend), `0.35` (cv-engine) | `app/core/config.py`, `cv-engine/config/settings.py` |
| IoU / NMS threshold | **Never set** — Ultralytics default `iou=0.7` NMS is used. Tracker association IoU is `0.25`. | `vehicle_detection_service.detect()`, `SimpleTracker(iou_threshold=0.25)` |
| Preprocessing | None before detection (raw BGR frame → YOLO letterbox). For OCR: upscale to 320px wide + grayscale + CLAHE(2.5, 8×8). | `app/services/ocr_service.py::preprocess_for_ocr` |
| Postprocessing | Class filter + confidence filter, then greedy-IoU tracking, then per-track plate vote aggregation | `vehicle_detection_service`, `simple_tracker`, `uploaded_video_service` |
| Object tracker | **Two of them**: backend `SimpleTracker` (greedy IoU, `max_misses=8`) for offline video; cv-engine `VehicleTracker` (ByteTrack-style, Kalman, PTS-driven) for live streams | `app/services/simple_tracker.py`, `cv-engine/tracking/vehicle_tracker.py` |
| **Number-plate detector** | **None.** There is no plate-localisation model at all. Plate "detection" is a *heuristic crop*: lower 55 % of the vehicle box (skipped for motorcycles) + the full padded vehicle box. | `app/services/ocr_service.py::extract_plate_crops`, `cv-engine/anpr/plate_detector.py` |
| OCR / ANPR | **RapidOCR (bundled ONNX, offline) first, EasyOCR fallback**, generic scene-text OCR — not plate-specific | `app/services/ocr_service.py::_ensure_engine` |
| Plate normalisation | `normalize_plate()` = uppercase + strip every non-alphanumeric. Indian pattern regex used only as a *plausibility discount*, never to invent characters. | `app/utils/plate_normalizer.py`, `cv-engine/anpr/normalizer.py` |
| Existing video processing | `uploaded_video_service._process_video()` — background thread per camera, in-memory job dict, one `VehicleEvent` per finished track | `app/services/uploaded_video_service.py` |
| Existing upload | `POST /api/uploads/videos` — **one file at a time**, one camera per file, `camera_id` supplied by the client | `app/api/uploads.py` |
| Existing API endpoints | `/cameras`, `/watchlist`, `/alerts`, `/detections`, `/events`, `/vehicles/{plate}[/events,/route]`, `/stats`, `/internal`, `/officers`, `/uploads`, `/evidence`, `/stream`, `/ws/events` | `app/main.py` |
| Dashboard components | `pages/Dashboard.tsx`, `components/dashboard/{KpiCard,Charts}` | — |
| Camera/video components | `components/camera/{CameraCard,CameraPlayer,UploadVideoModal,UploadedVideoPanel}` | — |
| Result / vehicle-log components | `components/vehicle/{DetectionTable,EvidencePanel,MovementTimeline,TraceSearchBar,VehicleInfoPanel}`, `pages/{Vehicles,VehicleInvestigation,Events}.tsx` | — |
| Camera geo-coordinates | **Yes** — `cameras.latitude/longitude` exist and drive the Leaflet map (`pages/GIS.tsx`, `components/gis/MapView.tsx`) | `app/database/models.py` |

## 2. Internal assessment (required summary)

- **Current vehicle detection model:** Ultralytics **YOLO11s**, COCO weights, `imgsz=640`, `conf=0.45`, classes = car / motorcycle / bus / truck. Not fine-tuned.
- **Current plate detection model:** **none** — a fixed geometric crop of the vehicle box.
- **Current OCR:** RapidOCR ONNX (fallback EasyOCR), generic scene text, single preprocessing variant.
- **Current tracker:** `SimpleTracker` — greedy IoU, `iou=0.25`, `max_misses=8` (offline); ByteTrack+Kalman in cv-engine (live).
- **Current video processing:** OpenCV `VideoCapture`, every 3rd frame, thread-per-video, in-memory job state (lost on restart).
- **Current backend:** FastAPI + SQLAlchemy + SQLite, routers dual-mounted on `/api` and `/api/v1`.
- **Current frontend:** React 19 + Vite + Tailwind, `/api` proxied by Vite to `localhost:8000`.
- **What can be reused (and is reused):** YOLO11 detector singleton, `SimpleTracker`, `ocr_service`, `normalize_plate`, `VehicleEvent` table, `Camera` registry, watchlist/alert engine, WS/SSE broadcast, Tailwind design system, `PlateLink`/`Panel`/`Modal` components, the `/vehicles/{plate}/…` investigation endpoints.
- **What needs improvement:**
  1. **No plate localisation** → OCR runs on a large vehicle crop, so the plate occupies <2 % of the pixels handed to the recogniser. *This is the bottleneck, not the vehicle detector.*
  2. Single OCR preprocessing variant, no super-resolution for small/far plates.
  3. No confidence tiering — a plate is either stored or dropped; nothing is labelled *Low confidence* / *Unknown*.
  4. Upload is single-file, no Google Drive input, job state is not persisted.
  5. No cross-video comparison, camera sequence, or vehicle-history aggregation.
  6. Detection provenance (frame number, bbox, detection confidence) is never stored.
- **What needs to be trained:** a **dedicated number-plate detector** (small YOLO fine-tuned on plate boxes cropped from the user's own footage). The **vehicle detector is kept as-is** (COCO YOLO11s already detects car/motorcycle/bus/truck reliably at CCTV distances); it is re-*evaluated* rather than re-trained, and only its thresholds are tuned. OCR is improved by better crops + multi-variant preprocessing rather than by retraining a recogniser.

## 3. Decision (Part 3)

| Component | Action | Why |
|---|---|---|
| Vehicle detector (YOLO11s) | **Keep. Evaluate + tune conf/IoU only.** Fine-tune *only* if evaluation on the user's footage shows recall < ~0.8. | Already good on COCO vehicle classes; retraining it would be the "blind YOLO upgrade" the brief forbids. |
| Number-plate detector | **Train a new one** (`yolo11n`-based, `imgsz=640`, plate class only) | It does not exist today — the single largest accuracy gap. |
| OCR engine | **Do not retrain.** Improve crop quality, add super-resolution + multi-variant preprocessing, add per-character confidence tiering and Indian-format validation. | Bottleneck is input quality, not the recogniser. |
| Tracker | Keep `SimpleTracker`, add class-consistency + per-track plate voting | Adequate for offline video; avoids new dependencies. |
| Thresholds | Re-derive `conf` / `iou` from the evaluation sweep | Cheap, measurable win. |
| Original weights | **Never overwritten** — backed up to `models/baseline/`, new weights written to `models/plate_detector.pt` | Brief §6. |
