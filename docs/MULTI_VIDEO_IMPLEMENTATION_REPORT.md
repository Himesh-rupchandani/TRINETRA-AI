# Multi-video vehicle & number-plate analysis — implementation report

Feature added to the existing TRINETRA AI project. Nothing was redesigned: the
existing OpenCV → YOLO11 → tracker → OCR pipeline, the existing SQLite/SQLAlchemy
database and the existing design system are reused. One new page and one new
sidebar entry; no existing page, route, style or endpoint was changed.

---

## 1. What was built

**Add videos** — multi-file local upload *or* a shared Google Drive link
(no Google account, no credentials, ever). The filename becomes the camera id
(`CAM1.mp4` → `CAM1`; collisions get `_2`, `_3`).

**Analyse** — each video runs through the project's own pipeline:

```
cv2.VideoCapture → frame sampling (every 5th frame)
  → vehicle detection   YOLO11s, COCO classes {car, motorcycle, bus, truck}
  → tracking            SimpleTracker, greedy IoU 0.25, 8-frame patience
  → plate localisation  NEW stage: fine-tuned model if present, else a
                        classical blackhat/Sobel/contour proposer
  → crop + preprocess   super-resolution + multi-variant thresholding
  → OCR                 RapidOCR (offline ONNX), EasyOCR fallback
  → normalisation       "GJ 01 AB 1234" → "GJ01AB1234"
  → ONE VehicleEvent per tracked vehicle (never one per frame)
```

**Compare across videos** — plates are grouped by normalised text and each
vehicle gets: the videos/cameras it was seen in, the count, the **observed**
camera sequence, the full timestamped history and summary statistics.

**Search** — one plate across all analysed videos, spacing/hyphens ignored.

### Endpoints (all under `/api/analysis`, also mounted at `/api/v1/analysis`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/videos/upload` | multi-file upload |
| POST | `/videos/gdrive/validate` | check a Drive link without downloading |
| POST | `/videos/gdrive` | download + register a shared Drive video |
| GET | `/videos` | list registered videos |
| DELETE | `/videos/{id}` | remove a video, its file and its sightings |
| POST | `/run` | start the pipeline |
| GET | `/status` | per-video progress |
| GET | `/results` | cross-video comparison |
| GET | `/search?plate=` | plate lookup |
| GET | `/vehicles/{plate}` | vehicle history |
| GET | `/videos/{id}/detections` | raw sightings from one video |
| GET | `/videos/{id}/file` | stream a stored video |

### Files

| New | |
|---|---|
| `app/api/video_analysis.py` | the 12 endpoints |
| `app/services/video_analysis_service.py` | registration, download, worker loop, storage |
| `app/services/plate_matching.py` | cross-video grouping, sequence, fuzzy suggestions |
| `app/services/plate_detector_service.py` | plate localisation (learned + classical) |
| `app/services/anpr_pipeline.py` | crop → OCR → normalise → multi-frame vote |
| `app/services/gdrive_service.py` | link parsing, probe, download, error messages |
| `tests/test_video_analysis.py` | the 17 scenarios |
| `trinetra-ai/src/pages/VideoAnalysis.tsx` + `src/components/analysis/*` | the UI |
| `trinetra-ai/src/services/videoAnalysisService.ts` | typed API client |
| `training/*` | footage analysis + dataset + training + evaluation toolkit |
| `docs/MULTI_VIDEO_ASSESSMENT.md` | PART 1/3 written assessment |

| Modified | Change |
|---|---|
| `app/database/models.py` | `VideoSource` table; `VehicleEvent` gains `video_id`, `frame_number`, `vehicle_confidence`, `bbox_json`, `plate_status` |
| `app/database/database.py` | additive per-column auto-migration (no data loss) |
| `app/core/config.py` | analysis/plate/OCR/matching settings, all with defaults |
| `app/main.py` | mounts the new router |
| `app/services/ocr_service.py` | plate preprocessing + **a concurrency fix** (below) |
| `app/services/vehicle_detection_service.py` | NMS IoU 0.7 → 0.55, shared inference lock |
| `src/app/router.tsx`, `src/components/layout/Sidebar.tsx` | one lazy route + one nav item |

---

## 2. Data-integrity rules (implemented, not aspirational)

* **One record per tracked vehicle**, not per frame. The largest-area frame of
  the track is the representative record; consecutive-frame duplicates never
  reach the database.
* **Confidence tiering.** `confidence = ocr_confidence × format_score`.
  Below `0.60` the read is discarded. `HIGH` needs an aggregate `≥ 0.80`
  **and** ≥ 2 agreeing reads **and** a canonical Indian plate format;
  otherwise `LOW_CONFIDENCE`, shown with a "Low confidence" chip.
* **Never invented.** No read at all → `plate_status = UNKNOWN`,
  `plate_number = NULL`. The vehicle is still counted as a sighting and simply
  cannot participate in matching.
* **Watchlist alerts fire only on `HIGH`.**
* **Fuzzy matching never merges.** Same length, exactly one differing
  character, and that difference must be a known OCR confusable
  (`0/O/D/Q`, `1/I/L/T`, `2/Z`, `5/S`, `6/G`, `8/B`, `4/A`, `U/V`, `M/H`, `C/G`).
  Skipped when both sides are `HIGH`. Surfaced separately as
  "Possible matches — not confirmed".
* **No geography is invented.** Each analysed video gets a `Camera` row with
  `latitude = longitude = NULL`, so the map cannot show a fake location. The UI
  shows the camera/video **sequence** only.
* **Sequence ordering is defensible.** Uploaded files carry no synchronised
  wall clock, so the order is: the order the videos were added, then the offset
  inside each video. Processing order (a race between worker threads) never
  decides a camera sequence.
* Existing demo/seed data is untouched and lives in different rows; every
  analysis row is linked to a `video_sources` entry.

---

## 3. Google Drive handling

`https://drive.google.com/file/d/<id>/view`, `/open?id=`, `/uc?id=` and
`docs.google.com/...` are all parsed. Validation happens **before** download and
returns a human sentence for every failure mode:

| Situation | Message |
|---|---|
| not a Drive URL | "That is not a Google Drive link." |
| folder link | "That link points to a Drive *folder*. Share the individual video file instead." |
| private file | "Google Drive returned a web page instead of the video. The file is most likely private — set sharing to 'Anyone with the link', or upload the file directly." |
| non-video | "'x.pdf' is not a supported video (.avi, .m4v, .mkv, .mov, .mp4, .webm)." |
| over the size limit | "Video exceeds the 250 MB limit." |
| no network / DNS / TLS failure | "Could not reach Google Drive from this server (ConnectError). Check the server's internet access, or download the video and upload the file directly." |

The virus-scan interstitial is handled by replaying its confirm form.
**Note:** this sandbox has no egress to `drive.google.com`, so the download path
could not be exercised against the live service here — the failure path above is
what it returns today, verified by test 5.

---

## 4. Real bugs found and fixed while verifying

1. **Lazy-singleton race (data-affecting).** `ocr_service._ensure_engine()` and
   `plate_detector_service._ensure_model()` set their `_attempted` flag *before*
   loading, with the fast-path check outside the lock. With several videos
   analysed in parallel, worker A loaded RapidOCR (~4 s) while workers B and C
   took the fast path, saw `_engine is None`, concluded "no OCR engine installed"
   and filed **every plate in their video as Unknown**. Observed live: 1 of 3
   videos read its plate. The flag is now set in a `finally` inside the lock;
   after the fix the same three videos read 3 of 3.
2. **`ANALYSIS_MAX_WORKERS` was not enforced.** Every queued video spawned a
   thread regardless of the setting, oversubscribing a 2-core box. A semaphore
   now bounds concurrent workers; extra videos stay `QUEUED` (visible in the UI).

3. **"Only one video came through" (data-affecting).** Registration gated on the
   filename extension (`.mp4 .avi .mov .mkv .webm .m4v`), so the containers real
   CCTV/DVR footage actually arrives in — `.3gp`, `.ts`, `.wmv`, `.dav`, a raw
   `.264` stream — were refused with *"unsupported video type"* and never
   entered the list. Reproduced against a running server: uploading
   `CAM1.mp4 + cctv1.3gp + cctv2.ts + cctv3.wmv + hik.264` registered **1**
   video. OpenCV/ffmpeg decide by *content*, not by name (all five decode), so
   the extension is now only a hint: obvious non-videos (`.txt`, `.pdf`, …) are
   still refused outright, everything else is probed. A clip the local OpenCV
   build cannot decode is re-encoded to H.264 MP4 with the bundled ffmpeg
   (`imageio-ffmpeg`, already a dependency) instead of being dropped, and each
   file is registered off the event loop so a slow conversion cannot stall the
   API. The same batch now registers **5 of 5**
   (`CAM1, CCTV1, CCTV2, CCTV3, HIK`). Files that still cannot be used are
   listed in *Videos in this analysis* as **Not added** rows with the exact
   reason, so a five-clip batch always accounts for five rows — nothing
   disappears silently. Covered by tests 20, 21, 21b and 22.

---

## 5. Verification

### Backend tests — `133 passed`

```
.venv/bin/python -m pytest TRINETRAAI/backend/tests -q     # 133 passed
```

`tests/test_video_analysis.py` covers the 17 required scenarios (17 passed):
multi-file upload · camera id from filename + collisions · invalid/mixed upload ·
invalid Drive link · private/unreachable Drive link · all videos processed ·
per-track de-duplication + full provenance · same plate matched across videos ·
sequence skips cameras that never saw it · single-video vehicle · ordered
timestamped history · low-confidence marking (and no alert) · unreadable → Unknown ·
fuzzy flagged not merged · plate search found/normalised/not-found · summary
statistics reconciled against stored rows · delete cascades + existing endpoints
unaffected.

The two model stages are stubbed there so the suite is deterministic; the real
models are exercised separately below.

### Frontend

`npm run typecheck` clean, `npm run lint` 0 errors (24 pre-existing warnings).

### End-to-end with the real models

Run against an **isolated database** (`/tmp/e2e/e2e.db`) so nothing synthetic
ever entered the product DB — verified: `video_sources = 0`,
`vehicle_events = 0` in `TRINETRAAI/trinetra.db`.

Three clips built by `training/tools/make_demo_clips.py`: real traffic frames
(Apache-2.0 `intel-iot-devkit/sample-videos`) with a **rendered plate composited
onto the detected vehicle**, because no available public clip has legible
plates at 768×432. Clearly synthetic, clearly labelled, used only to prove the
plumbing.

```
POST /api/analysis/videos/upload   CAM1.mp4 CAM2.mp4 CAM3.mp4   → 3 registered
POST /api/analysis/run                                          → CAM3 held QUEUED (2 workers)
GET  /api/analysis/status                                       → DONE 100 %, 1 vehicle each
GET  /api/analysis/results
```

| plate | status | videos | sequence | best OCR |
|---|---|---|---|---|
| `GJ01AB1234` | HIGH | 2 | **CAM1 → CAM3** | 0.987 |
| `MH12XY4567` | HIGH | 1 | CAM2 | 0.997 |

`total_sightings 3 · readable 3 · unique_plates 2 · plates_in_multiple_videos 1`.
`GET /api/analysis/search?plate=gj01ab1234` → `CAM1 → CAM3`. CAM2 never saw that
plate and never appears in its sequence — the exact acceptance case.

**These numbers describe a synthetic fixture and say nothing about real-world
accuracy.** Real accuracy can only come from your footage.

---

## 6. Training track (PARTS 2–7) — toolkit ready, waiting on your footage

The repository contained no traffic video, so no model was fine-tuned: training
on someone else's clip and reporting the result as yours would be fabricated.
Everything needed is in `training/` (see `training/README.md`):

| Script | Part | Does |
|---|---|---|
| `analyze_video.py` | 2 | resolution/fps/codec, lighting & night/IR, blur risk, traffic density, classes present, vehicle and **estimated plate pixel height**, occlusion, geometry → recommendations |
| `extract_frames.py` | 4 | representative frames, near-duplicates dropped, **time-segment split** (train/val/test) with a manifest |
| `autolabel_plates.py` | 4 | machine-proposed plate boxes + a review report — proposals, not ground truth |
| `build_dataset.py` | 4 | validates labels and **fails on any segment that leaked across splits**; emits the data yaml |
| `train_plate_detector.py` | 5 | fine-tunes **only** the plate detector; backs originals up to `models/baseline/`; saves a **new** `models/plate_detector.pt`; CPU/GPU-appropriate defaults |
| `evaluate.py` | 6–7 | baseline vs fine-tuned on the held-out test split: P/R/F1/TP/FP/FN, mAP50, mAP50-95, small-plate breakdown, OCR exact-match/CER/refusals |

The chain was smoke-tested end to end (extract → autolabel → validate →
evaluate) and works; `build_dataset.py` correctly reported "OK — splits are
clean and leakage-free".

**PART 3 decision** (`docs/MULTI_VIDEO_ASSESSMENT.md`): keep the COCO YOLO11s
vehicle detector (tuning only), **do not** retrain OCR, and train the missing
**plate-localisation** stage — that is the weak component. This is re-checkable
against your footage with `analyze_video.py` before anything is trained.

Ran on the stand-in clip `person-bicycle-car-detection.mp4` (768×432, 12 fps):
median estimated plate height **17.9 px**, 33 % below 16 px, blur risk medium.
That is below the readability floor — which is precisely why the assessment
recommends fixing localisation and crop quality, not retraining the recogniser.

---

## 7. What I need from you

1. **Your footage** — 2–4 real clips (ideally the same vehicle passing more than
   one camera). Then PARTS 2–7 run for real: footage report, dataset, fine-tune,
   baseline-vs-fine-tuned metrics.
2. **Drive links** (shared "Anyone with the link") if you want that path
   exercised against the live service — this sandbox cannot reach
   `drive.google.com`.
3. Whether you want a per-video **recording start time** field. Today the
   cross-video order is "order added + offset in video"; with real recording
   timestamps the sequence would become a true chronological path.

## 8. Try it

Backend on `:8000`, frontend on `:5173` → **Video Analysis** in the sidebar.
Upload 2–3 clips, press *Start analysis*, watch the per-video progress, then
read the cross-video table and search a plate.
