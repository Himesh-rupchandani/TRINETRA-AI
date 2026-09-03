# TRINETRA AI — CV Engine

**Intelligent Vision. Faster Response.**

The AI / computer-vision engine of the Trinetra hybrid CCTV platform. It consumes
Sentinel camera streams, detects and tracks vehicles (YOLO11 + ByteTrack), reads
plates (PP-OCR/EasyOCR), and publishes well-formed sighting events to the backend
(`POST /api/events`) with evidence frames, de-duplication, confidence handling and
resilient reconnection.

The full pipeline:

```
Sentinel Camera -> Frame -> Detection -> Tracking -> ANPR -> Event JSON
                -> Dedup -> Evidence -> POST /api/events -> Backend
```

---

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # or scripts/install_dev_env.sh
.venv/bin/python scripts/fetch_models.sh         # yolo11n.pt into ./models
.venv/bin/python scripts/run_demo.py             # offline demo (fixture)
.venv/bin/python -m pytest -q                    # 95 tests, offline
```

Run the real thing (needs egress to the government gateway):

```bash
.venv/bin/python scripts/list_cameras.py                 # what exists
.venv/bin/python scripts/probe_camera.py cam04           # measured stream behaviour
.venv/bin/python scripts/run_pipeline.py --cameras cam04 --seconds 60
```

---

## Layout

```
capture/     catalogue client, RTSP/HLS/file capture, PTS, reconnect
detection/   YOLO11 wrapper + vehicle class mapping + inference gate
tracking/    ByteTrack wrapper + hard scene-cut detection
anpr/        OCR engines, plate detector, normalizer, confidence, aggregator
events/      stable event schema, builder, de-duplicator
evidence/    deterministic evidence frame writer
integration/ backend client (queue + bounded retry + dead-letter)
pipeline.py  the core loop (CameraPipeline + run_camera)
metrics.py   real timers + psutil/torch resource snapshot
scripts/     CLI: list/probe/run/demo/benchmark + model/fixture fetchers
tests/       offline unit + integration tests (live tests gated by TRINETRA_LIVE=1)
```

---

## Design rules that matter

* **PTS is the only video clock.** Never frame arrival time, never
  `CAP_PROP_FPS`. `capture/frames.py` builds a monotonic `continuous_ms` that
  survives looping feeds; the tracker ages tracks in PTS seconds.
* **RTSP over TCP** for inference; **HLS as fallback** when RTSP can't open. The
  transport that actually produced a frame is stamped on it.
* **Reconnect** 2->4->8->16->30s with jitter, reset after a stable connection; a
  connection that opens but sends nothing also backs off (no hot loop).
* **Scene cuts reset tracking.** Looping feeds must not carry impossible tracks.
* **Confidence is carried, not faked.** A low-confidence plate is stored and
  flagged, never promoted. Every normaliser substitution is recorded.
* **One sighting per vehicle per camera per window** — 500 frames do not become
  500 events. Different cameras always produce their own sightings.
* **Backend failures never stall the pipeline** — events queue, retry with
  bounded backoff, then land in a dead-letter file.

---

## Event contract

The ten core field names in `events/event_schema.py::CORE_EVENT_FIELDS` are the
stable contract (`camera_id`, `vehicle_id`, `plate_raw`, `plate`,
`plate_confidence`, `timestamp_pts`, `event_time`, `latitude`, `longitude`,
`vehicle_class`, `evidence_ref`). Extra context (track_id, confidence_grade,
source_transport ...) is additive only.

---

## Demo vs live

* **DEMO MODE** — `scripts/run_demo.py` and `tests/integration/test_offline_e2e.py`
  run the *real* AI on a stored fixture, offline. Clearly labelled, never mistaken
  for government footage.
* **LIVE MODE** — `scripts/run_pipeline.py` / `tests/integration/test_live_sentinel.py`
  (gated by `TRINETRA_LIVE=1`) against the real catalogue. The government demo must
  use this path.

---

## Environment

Configuration is environment/`.env` driven (see `.env.example`). Nothing secret is
ever read, logged, or committed. Model weights and runtime output live in
gitignored `./models` and `./var`.
