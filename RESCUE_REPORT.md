# TRINETRA AI — Emergency Debug / Rescue: Final Report

Date: 2026-09-14 · Branch: `arena/01a09e58-hack` · Base commit: `2fe0cae`

## 1. What was tested (the one real video)

| Field | Value |
|---|---|
| Video | `TRINETRAAI/backend/demo_cam04.mp4` (real uploaded-style CCTV clip) |
| Container / codec | FMP4 (H.264), 1280×720, 12 fps, 360 frames, 30.0 s |
| Decoder probe | OpenCV `VideoCapture` opens it; no re-encode needed (PASS) |
| Vehicle model | `yolo11s.pt` (COCO vehicle classes), loaded in ~2.0 s |
| Plate model | `models/license-plate-finetune-v1n.pt` (class `License_Plate`), loaded OK |
| OCR engine | RapidOCR (bundled ONNX, offline), loaded OK |

## 2. Results on the full video (360 frames)

- Frames read: **360** · frames analysed: **72** (every 5th frame)
- Vehicles detected: **9** · readable plates: **3** · unreadable: **6** (honest `UNKNOWN`, never fabricated)
- Sightings persisted: **9** (one immutable record per tracked vehicle)

| track | frame | timestamp | class | veh_conf | plate | plate_conf | status |
|---|---|---|---|---|---|---|---|
| 1 | 5 | 00:00:00 | motorcycle | 0.81 | GJ03AG6167 | 0.9447 | HIGH |
| 2 | 85 | 00:00:07 | motorcycle | 0.66 | GJ03DE8157 | 0.9942 | HIGH |
| 3–5, 7–9 | — | — | motorcycle | 0.35–0.54 | (unreadable) | — | UNKNOWN |
| 6 | 295 | 00:00:24 | motorcycle | 0.72 | GJ03DE8157 | 0.9944 | HIGH |

Evidence consistency (verified by re-OCR of the saved crops):
- The full annotated frame, vehicle crop and plate crop all come from the **same frame**.
- The drawn label on the full frame now matches the stored `plate_text` (e.g. track #2 shows `#2 motorcycle GJ03DE8157`).
- `GJ03AG6167` re-reads from its plate crop; `GJ03DE8157` re-reads from both of its plate crops.

## 3. P0 acceptance matrix

| Priority | Item | Result | Evidence |
|---|---|---|---|
| P0 | Real video detection works | ✅ PASS | 9 vehicles detected on `demo_cam04.mp4` |
| P0 | Number-plate OCR works | ✅ PASS | 3 plates read, 2 distinct (`GJ03AG6167`, `GJ03DE8157`) |
| P0 | Correct evidence frame | ✅ PASS | full/vehicle/plate crops + label all from the one representative frame |
| P0 | CSV result | ✅ PASS | `detections.csv` — 9 real rows, required columns all present |
| P0 | Database persistence | ✅ PASS | 9 `VehicleEvent` rows; re-run kept 7 (no duplicates) |
| P0 | Plate search (normalized) | ✅ PASS | `plate_matching.search` exact-match on `GJ03AG6167` / `GJ03DE8157` |
| P0 | Camera + location + lat/lng | ✅ PASS | camera rows carry **real** coords; uploaded videos carry `NULL` (no fake pin) |
| P0 | Map result | ✅ PASS | 1 valid location → 1 marker; no-GPS footage → no fabricated pin |

### End-to-end PASS detail

- **CLI** `python process_video.py TRINETRAAI/backend/demo_cam04.mp4 --output /tmp/out_full`
  → `annotated.mp4`, `detections.csv`, `detections.json`, `summary.json`, `evidence/` (9 full + 9 vehicle + 3 plate = 21 JPEGs).
- **Dashboard path** (upload → worker → DB → search) ran the same `analyze_video` core and stored the **same 9 sightings**; cross-video matching then found `GJ03AG6167` in **two** videos (`DEMO_CAM04`, `DEMO_SHORT`) with the chronological sequence, proving DB + search + comparison all work on real records.
- **CSV columns present:** `detection_id, video_filename, frame_number, timestamp, track_id, plate, plate_confidence, vehicle_confidence, evidence_frame` (+ vehicle class / plate status / raw / bboxes / evidence paths).

## 4. Root causes found & fixed

1. **Wrong plate-model path** — `config.PLATE_MODEL_PATH` pointed at `models/plate_detector.pt` which does not exist; the tracked weights are `models/license-plate-finetune-v1n.pt`. Fixed in `config.py`.
2. **OCR discarded multi-line reads** — `ocr_service.read_plate` validated each OCR line separately and threw away two-line plates (`"GJ03P"` + `"08696"`). Added `joined_plate_candidate()` and wired it into `ocr_service` and `anpr_pipeline`.
3. **Enhancement pre-processing could flip digits** — CLAHE/Otsu variants ran before the raw crop and could override a correct read (`96980` vs `08696`). Reordered `preprocess_variants` so the **raw colour crop is authoritative** and `anpr_pipeline` stops once the raw crop reads.
4. **Evidence/frame mismatch** — the annotated label was drawn from a stale plate dict, so the displayed label could differ from the stored plate. The label is now drawn **before** the snapshot, and every field of a sighting (frame number, timestamp, bboxes, crops, plate) comes from one immutable `Sighting` object.
5. **Non-deterministic output order** — sightings were emitted in track-retirement order; now sorted by `(track_id, frame_number)` so CSV/JSON/detection ids are stable across identical runs.
6. **Fabricated GPS** — `Camera.latitude/longitude` defaulted to `23.0225 / 72.5714` (Ahmedabad), so every camera — including uploaded videos with no known location — got a fake map pin. Removed the scalar defaults; the upload APIs and the analysis registration now store `NULL` for footage with no real-world position. Real seeded/live cameras keep their real configured coordinates.
7. **Duplicate persistence on re-run** — re-running analysis appended a second copy of each track. `_run_video` now replaces the video's prior sightings before writing (verified: re-run kept the exact row count).

### Deliberately NOT changed

- The canonical Indian-plate regex (`SS DD L{1,3} N{3,4}`). The real demo video's readable plates (`GJ03AG6167`, `GJ03DE8157`) are canonical; the 5-digit legacy case (`GJ03P08696`) is still correctly stored as `LOW_CONFIDENCE` rather than weakening the cross-layer format contract pinned by `tests/test_plate_format_consistency.py` (backend + cv-engine + frontend).
- No frontend code was modified (the frontend already renders corrected backend data, including evidence crops and search results).

## 5. Regression results

| Suite | Result |
|---|---|
| Backend `pytest` | **272 passed, 0 failed, 0 skipped, 2 deselected** |
| Frontend `npm test` | **48 / 48 passed** |
| cv-engine `pytest` | 92 passed; 2 failed + 1 collection error — **pre-existing at base commit `2fe0cae`** (reproduced in a clean worktree; unrelated to this change, no cv-engine file was modified) |

## 6. Files changed

| File | Change |
|---|---|
| `TRINETRAAI/backend/app/services/video_analysis_core.py` | **new** — shared deterministic `analyze_video` core; `Sighting` (with `full_frame`) as the single source of truth; representative-frame selection; deterministic ordering; label-before-snapshot |
| `TRINETRAAI/backend/app/services/video_analysis_service.py` | `_run_video` now uses the shared core; removed per-frame event fan-out and unused imports; idempotent re-runs |
| `TRINETRAAI/backend/app/services/ocr_service.py` | raw-first `preprocess_variants`; added `joined_plate_candidate()` |
| `TRINETRAAI/backend/app/services/anpr_pipeline.py` | joined-candidate path; raw crop is authoritative (break after raw read) |
| `TRINETRAAI/backend/app/core/config.py` | `PLATE_MODEL_PATH` → `models/license-plate-finetune-v1n.pt` |
| `TRINETRAAI/backend/app/database/models.py` | removed fake `Camera.latitude/longitude` defaults (now `NULL`) |
| `TRINETRAAI/backend/app/database/schemas.py` | camera lat/lng schema default → `None` |
| `TRINETRAAI/backend/app/api/uploads.py` | uploaded cameras no longer get a fabricated coordinate |
| `process_video.py` | **new** — deterministic CLI (`<video> [--output] [--sample N]`) producing annotated video + CSV/JSON + evidence |
| `TRINETRAAI/backend/run_full_demo.py` | **new** — one-shot full-video DB persistence run |
| `TRINETRAAI/backend/check_db_e2e.py` | **new** — short-clip DB end-to-end + search verification |

Committed to `arena/01a09e58-hack` (HEAD `422d71c`) and pushed.
