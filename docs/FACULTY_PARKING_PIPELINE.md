# Recorded-video ANPR pipeline (Faculty Parking demo)

Real video → real detections → real tracks → real OCR → **distinct sighting events**.

This document covers the offline/recorded-video path added to `cv-engine`. It reuses the
live engine's modules (detector, tracker, ANPR aggregation, event contract, evidence
writer conventions) and adds only what a *file* needs that a live stream does not.

---

## 1. What was added (and what was deliberately not touched)

| New | Purpose |
|---|---|
| `capture/file_capture.py` | `probe_video()` (measured properties, never assumed) + `VideoFileSource` yielding the existing `FramePacket` |
| `anpr/plate_yolo.py` | YOLO single-class **licence-plate region** detector (optional; falls back to the existing heuristic crops) |
| `sightings/segmenter.py` | FRAME vs TRACK vs **SIGHTING** logic, multi-frame OCR voting, ID-switch merging |
| `sightings/quality.py` | measurable evidence quality (plate area, sharpness, OCR confidence, edge distance) |
| `sightings/reporting.py` | evidence files, CSV/JSON, backend events, target-vehicle report |
| `pipeline/video_pipeline.py` | the offline orchestration loop + annotated-video rendering |
| `scripts/analyze_video_file.py` | CLI runner (all knobs exposed) |
| `scripts/run_faculty_parking.sh` | sample-pass → confirm → full-pass demo loop |
| `scripts/post_sightings.py` | backend handoff (`POST /api/v1/events`), with `--dry-run` |
| `scripts/setup_video_env.sh` | environment + model weights with SHA-256 verification |
| `scripts/make_multivisit_fixture.py` | builds a multi-visit validation clip out of real footage |
| `tests/test_file_capture.py`, `tests/test_sighting_segmentation.py`, `tests/test_video_reporting.py`, `tests/test_detection_tracking_contract.py`, `tests/test_video_events_backend_contract.py` | unit coverage for all of the above |

**Not touched:** frontend, theme, dashboard, alerts UI, GIS, backend architecture and
backend business logic. The only backend interaction is *consuming* two existing
interfaces: `app.services.gdrive_service.download()` and `POST /api/v1/events`.

---

## 2. Models used (no training was performed)

| Stage | Model | Provenance / integrity |
|---|---|---|
| Vehicle detection | **YOLO11-nano** (`yolo11n.pt`, COCO) — classes car / motorcycle / bus / truck via the repo's existing `detection/classes.py` | sha256 `0ebbc80d…44ee1`, identical to the official Ultralytics `v8.3.0` asset |
| Tracking | repo's existing **ByteTrack-style** `tracking/vehicle_tracker.py` (two-stage IoU association + Kalman, PTS-driven) | in-repo |
| Plate detection | single-class **YOLO licence-plate detector** (`license_plate_detector.pt`) | sha256 `8ec3b254…c51b0` |
| OCR | **RapidOCR** (ONNX, models bundled in the wheel → fully offline). EasyOCR selectable with `--ocr-engine easyocr` | in-repo `anpr/ocr.py` |

Nothing was fine-tuned on the demo video: the pipeline must generalise to other Rajkot
location videos. `yolo11s`/`yolo11m` can be dropped in with `--vehicle-model` when a GPU
is available — no code change.

---

## 3. Frame vs track vs sighting

```
vehicle visible 8 s  →  ~200 frames  →  1 track  →  1 SIGHTING
vehicle leaves, returns 40 s later    →  new track  →  2nd SIGHTING
```

Two configurable mechanisms decide sighting boundaries:

* `--track-end-gap` (`TRACK_END_GAP_SECONDS`, default **2.0 s**) — an open sighting closes
  when its track has not been observed for that long.
* `--sighting-cooldown` (`SIGHTING_COOLDOWN_SECONDS`, default **3.0 s**) — if the *same
  normalized plate* reappears within this window (or overlaps in time), the fragment is
  merged back into the previous sighting. This absorbs tracker ID-switches and duplicate
  boxes instead of inflating the count.

False-positive controls: minimum 3 observed frames and 0.3 s duration per sighting,
minimum plate crop width (26 px), minimum vehicle box area (3000 px²), OCR confidence
floor, plate-format plausibility check, and per-track plate scoping (a read can only ever
attach to the track it was cropped from).

## 4. Multi-frame OCR voting

Per track, candidates are grouped by normalized text; the winner is the cluster with the
most agreeing reads (ties → higher mean confidence), and the reported confidence is
`0.5·max + 0.5·mean` (the repo's existing `anpr/confidence.aggregate_readings`). A single
read is never trusted: with fewer than `--min-agree-reads` (default 2) supporting frames,
or below `--plate-reject-threshold` (default 0.60), the sighting is marked
`UNCERTAIN` — kept and visible, never silently promoted, never fabricated. Sightings with
no plate at all are `NOT_DETECTED`.

Raw OCR text is always preserved next to the normalized value
(`"CA 455-822"` → `"CA455822"`).

---

## 5. Running it

```bash
# one-time: environment + weights (verified by SHA-256)
bash cv-engine/scripts/setup_video_env.sh

# guided demo loop: 25 s sample first, then the full video
bash cv-engine/scripts/run_faculty_parking.sh /path/to/faculty_parking.mp4

# or straight from a public Google Drive link (uses the backend's gdrive_service)
bash cv-engine/scripts/run_faculty_parking.sh --drive-url "https://drive.google.com/file/d/<ID>/view"

# any other location video, same architecture
python cv-engine/scripts/analyze_video_file.py rajkot_gate2.mp4 \
    --location "Rajkot Gate 2" --camera-id rajkot_gate2 --frame-skip 3
```

### Output layout

```
outputs/<video_id>/
├── annotated_video.mp4        boxes, TRACK id, class, plate + confidence, timestamp,
│                              and SIGHTING #n markers for the target vehicle
├── vehicle_sightings.csv
├── vehicle_sightings.json     per-sighting rows incl. every competing OCR candidate
├── target_vehicle_report.json the exactly-N-sightings report (honest when not found)
├── events.json                backend-ready POST /api/v1/events payloads
├── summary.json               measured video properties + run metrics
├── evidence/
│   ├── sighting_01.jpg        best evidence frame (measurable quality score)
│   └── sighting_01_plate.jpg  plate crop, when one was detected
└── logs/processing.log
```

`event_time` in `events.json` is **null**: a recorded upload carries no real capture
clock. Video timing lives in `timestamp_pts` (milliseconds, container PTS).

### Performance knobs

`--frame-skip` (default 2), `--imgsz`, `--conf`, `--plate-conf`, `--ocr-interval-ms`,
`--max-ocr-per-frame`, `--max-reads-per-track`, `--min-plate-width`, `--min-vehicle-area`.

Measured on this 2-core CPU sandbox (no GPU), 1280×720 source, `frame-skip 2`,
yolo11n @640 + plate detector @320 + RapidOCR: **≈0.39 s per processed frame**
(≈0.21× realtime). A GPU or `--frame-skip 3` moves this proportionally; detection
accuracy is not traded away for FPS by default.

---

## 6. Validation performed

1. **Ingestion** — `probe_video()` measured resolution, reported vs delivered FPS,
   frame count, duration and codec on three real clips; unit tests cover frame-skip,
   analysis windows, truncated files and unopenable files.
2. **Detection/tracking/ANPR on real footage** — 8 s sample of real traffic footage:
   344 detections, 9 tracks, 8 sightings, plate `CA455822` read at 0.84 confidence.
   Manual check against the evidence crop: the real plate is `CA 455-822` → **correct**.
3. **Five-sighting logic on real footage** — because the Faculty Parking video is not
   reachable from this environment (see §7), a multi-visit fixture was assembled from
   *real* footage (`scripts/make_multivisit_fixture.py`): the same vehicle enters and
   leaves five times, separated by 5 s of unrelated real footage.

   Result (`outputs/multivisit_fixture/`):

   ```
   CA455822 → 5 sightings   (max conf 0.8455)
   SIGHTING 1  t=00:00.1  track 1
   SIGHTING 2  t=00:10.6  track 13
   SIGHTING 3  t=00:21.2  track 24
   SIGHTING 4  t=00:31.8  track 35
   SIGHTING 5  t=00:42.3  track 46
   ```

   The five constructed visits start at 0.0 / 10.6 / 21.1 / 31.7 / 42.2 s — every
   sighting boundary matches, each visit produced exactly one sighting (not 138 frames
   worth), and each has its own track id and evidence frame. All five evidence frames and
   plate crops were inspected manually: same vehicle, same plate, five separate visits.
4. **Tests** — `python -m pytest cv-engine/tests -q` → 119 passed.

> The fixture is a **validation artifact**, clearly labelled as such. It is not, and must
> not be presented as, the Faculty Parking result.

---

## 7. Known blocker: the Faculty Parking video

The Drive file (`VID_20260907_114106.mp4`, 172 MB) **cannot be downloaded inside this
sandbox** — egress is restricted to PyPI and GitHub, so every Google host fails at the TLS
layer:

```
Google Drive download failed: Could not reach Google Drive from this server
(ConnectError). Check the server's internet access, or download the video and
upload the file directly.
```

The code path itself is finished and wired to the backend's existing `gdrive_service`.
On any machine with normal internet, this single command produces the full deliverable
set for the real video:

```bash
bash cv-engine/scripts/run_faculty_parking.sh \
    --drive-url "https://drive.google.com/file/d/17azT2_fcJu7YLobhJZmBF_TjvLd2_2ES/view"
```

Alternatively, place the file anywhere locally and pass its path.

---

## 8. Backend handoff

```bash
python cv-engine/scripts/post_sightings.py outputs/faculty_parking/events.json --dry-run
python cv-engine/scripts/post_sightings.py outputs/faculty_parking/events.json \
    --backend-url http://localhost:8000
```

Payloads are validated against the engine-side contract and, in the test suite, against
the backend's real `VehicleEventCreate` pydantic schema — if either side renames a field,
`tests/test_video_events_backend_contract.py` fails.
