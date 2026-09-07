# TRINETRA AI — cv-engine

**Intelligent Vision. Faster Response.**

The AI/Computer-Vision engine of TRINETRA AI: consumes real **Sentinel** CCTV
feeds, runs vehicle detection → tracking → ANPR, and delivers validated
vehicle sighting events to the backend (`POST /api/events`), enabling
watchlist matching, alerts, and multi-camera vehicle traces.

```
Sentinel Camera → Frame(PTS) → YOLO11 Detection → ByteTrack-style Tracking
   → Plate Crop → EasyOCR → Confidence + Normalization → Multi-frame Aggregate
   → Event Builder → Dedup → Evidence → POST /api/events → Watchlist → Alert
```

> **Scope note:** the backend (`TRINETRAAI/backend`) already implements event
> ingestion, watchlist, alert dedup, GIS routes and Sentinel catalogue sync.
> cv-engine is the *CV side*: it never reimplements backend logic and keeps
> the event contract identical to the backend's `VehicleEventCreate` schema.

---

## Quick start

```bash
cd cv-engine
python -m venv .venv && source .venv/bin/activate
# CPU-only torch first (recommended on hackathon hardware):
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# If cv2 later fails with "libGL.so.1: cannot open shared object file",
# the GUI opencv wheel overwrote the headless build — fix with:
#   pip uninstall -y opencv-python && pip install -q opencv-python-headless

# 1. Inspect the Sentinel catalogue + suggested diverse test subset
python scripts/check_catalogue.py

# 2. Run the pipeline on ONE real camera (Day-1 definition of done)
python scripts/run_pipeline.py --mode live --camera cam04 --duration 120

# 3. Scale out: catalogue-diverse subset (codecs/resolutions/statuses)
python scripts/run_pipeline.py --mode live --subset 3 --duration 300
```

### Live mode needs your Sentinel credentials

`run_pipeline.py --mode live` reads the catalogue and builds authenticated RTSP
URLs from the same env vars as the backend. They are read from the **process
environment** (no `.env` auto-load here), so export them in the shell first —
the `@` in the email may be written plainly, it is percent-encoded as `%40`
when the URL is built:

```bash
export SENTINEL_EMAIL=alice@example.com     # your registered email
export SENTINEL_PASSWORD='your access password'
# optional overrides (defaults match the integrator guide §1):
# export SENTINEL_CATALOGUE_URL=https://cctv.corp8.cloud/cameras.json
# export SENTINEL_RTSP_HOST=103.250.160.189
# export SENTINEL_RTSP_PORT=8554
export BACKEND_BASE_URL=http://127.0.0.1:8000   # where TRINETRA backend listens

python scripts/run_pipeline.py --mode live --camera cam04 --duration 120
```

Expected failures, decoded:

| Symptom | Cause → fix |
|---|---|
| `CATALOGUE UNREACHABLE: ...` | `cctv.corp8.cloud` not reachable from this network (it is Cloudflare-fronted and was blocked in this sandbox). Run on the venue/allowed network. |
| RTSP logs show `401 Unauthorized` | Email/password wrong, or not on the approved access list. Check `SENTINEL_EMAIL`/`SENTINEL_PASSWORD` are exported. |
| RTSP connect refused/timeouts on TCP | Port `8554/TCP` closed on your path → the guide says fall back to HLS (`ALLOW_HLS_FALLBACK=true` is the default). |
| `libGL.so.1` on import cv2 | GUI `opencv-python` overwrote headless cv2 → `pip uninstall -y opencv-python && pip install -q opencv-python-headless` |

### Demo mode (NOT live Sentinel)

Scripted fixtures exercising the full plumbing (tracking → ANPR aggregation →
dedup → evidence → backend POST). Useful for CI and offline demos; the
Government-feed demo must always use `--mode live`.

```bash
python scripts/run_pipeline.py --mode demo --backend-url http://localhost:8000
```

---

## Layout

| Module | Responsibility |
|---|---|
| `capture/sentinel_catalogue.py` | catalogue fetch/parse, `Camera` object, `get_cameras()`/`get_camera()`, diverse test-subset selection |
| `capture/rtsp_capture.py` / `hls_capture.py` | RTSP-over-TCP capture, HLS fallback |
| `capture/stream_capture.py` | PTS extraction, scene-discontinuity detection, degraded/reconnect states |
| `capture/reconnect.py` | exponential backoff (2→4→8→16→cap 30s), `ManagedCapture` loop |
| `detection/vehicle_detector.py` | YOLO11 vehicle-only detection (car/motorcycle/bus/truck) |
| `tracking/vehicle_tracker.py` | PTS-driven Kalman + two-stage IoU association (ByteTrack-style) |
| `anpr/` | plate crops, EasyOCR wrapper, normalization, confidence tiers, per-track multi-frame aggregation |
| `events/` | stable event schema, event builder, camera+track+plate dedup |
| `evidence/evidence_writer.py` | deterministic full-frame + plate-crop JPEG evidence |
| `integration/backend_client.py` | queued non-blocking POST with retries/backoff + dead-letter |
| `pipeline/camera_pipeline.py` | one camera's full loop |
| `scripts/` | runner, catalogue probe, benchmark, ANPR validation |

---

## Timing contract (non-negotiable)

* **PTS is the only video clock.** `FramePacket.pts_ms` comes from the
  container (`CAP_PROP_POS_MSEC`); if a muxer doesn't expose it, a monotonic
  stream clock is used — never wall-clock arrival time, never
  `frame_number / FPS`, and `CAP_PROP_FPS` is diagnostic-only.
* The tracker receives **PTS deltas**; track ages and suppression windows are
  measured in PTS-ms.
* `event_time` (wall clock) is the real-world anchor stored by the backend;
  `timestamp_pts` carries the video timeline.

## Scene discontinuities

Sentinel feeds loop. PTS rollbacks (>0.5 s backwards), large gaps (>5 s),
content-level hard cuts and reconnects all flag `is_discontinuity`; the
pipeline then **resets tracking + plate memory + dedup state** instead of
carrying invalid long-lived tracks. Looping is normal, not an application
failure.

## Confidence policy (no fake certainty)

* `plate_confidence` is always propagated.
* Readings below `ANPR_CONF_THRESHOLD` (default 0.60) are rejected — the
  sighting can still emit, plateless.
* Readings between the reject threshold and `ANPR_LOW_CONF_MARK` (0.80) are
  kept and remain *marked low* — never silently upgraded.
* Multi-frame aggregation: agreeing reads win over single outliers;
  aggregate = 0.5·max + 0.5·mean (spec example: 0.81/0.91/0.95 → 0.92).

## Event contract (stable)

```json
{
  "camera_id": "cam04",
  "vehicle_id": 17,
  "plate_raw": "GJ 01 AB-1234",
  "plate": "GJ01AB1234",
  "plate_confidence": 0.94,
  "timestamp_pts": 123456.78,
  "event_time": "2026-09-02T14:32:18Z",
  "latitude": 23.0001,
  "longitude": 72.5001,
  "vehicle_class": "car",
  "evidence_ref": "cam04/cam04_17_123456ms_GJ01AB1234.jpg"
}
```

Field names are owned by `events/event_schema.py` and mirror the backend's
`VehicleEventCreate` exactly — a contract test fails if either side drifts.
Location comes **only** from camera metadata; nothing is inferred from video.

## Configuration (env)

`SENTINEL_CATALOGUE_URL`, `BACKEND_BASE_URL`, `MODEL_PATH`, `CONF_THRESHOLD`,
`ANPR_CONF_THRESHOLD`, `FRAME_SKIP`, `RECONNECT_MIN`, `RECONNECT_MAX`,
`EVIDENCE_DIR`, plus: `INFERENCE_IMGSZ`, `CV_DEVICE`, `PROCESS_INTERVAL_MS`,
`ANPR_INTERVAL_MS`, `EVENT_SUPPRESSION_SEC`, `TRACK_MAX_AGE_SEC`, `LOG_LEVEL`…
(full list in `config/settings.py`). No secrets are ever hard-coded.

## Training a Gujarat-CCTV detector (fine-tune, not from scratch)

The stock model is **YOLO11s (COCO)**. Fine-tune it on the Drive traffic clip
rather than training a new architecture. A separate 1-class plate detector
feeds OCR. Full write-up, commands, and footage analysis:

```
python training/prepare_all.py --video feeds/reference_traffic.mp4
python training/train_vehicles.py --model models/original/yolo11s.pt --device 0
python training/train_plates.py   --model yolo11n.pt --device 0
python training/infer_video.py    --video feeds/reference_traffic.mp4
```

See [`training/README.md`](training/README.md). The original `yolo11s.pt` is
copied to `models/original/` and never overwritten; the live pipeline picks up
`models/trained/vehicles/best.pt` automatically.

## Tests

```bash
pytest                     # offline suite (unit + fixture integration)
TRINETRA_LIVE=1 pytest -m live tests/test_live_sentinel.py -v   # real feed
```

The offline suite includes an end-to-end integration test that runs the demo
scenario against a **real backend instance** (uvicorn + SQLite) and verifies
event → watchlist match → alert. Live Sentinel tests are separate, marked
`live`, and are never simulated.

## Known limitations (stated, not hidden)

* Some muxers don't expose `CAP_PROP_POS_MSEC`; the monotonic fallback keeps
  ordering correct but loses absolute container timestamps.
* EasyOCR on CPU is the ANPR latency bottleneck — see `scripts/benchmark.py`.
* ANPR quality depends entirely on how many pixels the plate occupies in the
  Sentinel stream; measure with `scripts/validate_anpr.py --images <dir>`.
