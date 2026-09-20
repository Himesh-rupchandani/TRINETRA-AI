# Live plate notifications and Vehicle Log

The backend now connects actual live detections to the existing event pipeline:

```
Playing camera / resident stream
  → sampled frame → vehicle detector (up to 3 vehicles)
  → tracking → localized plate crop → OCR → multi-frame agreement
  → VehicleEvent + evidence → SSE/WebSocket
  → plate notification + camera history + Vehicle Log
```

## Run it

Use a persistent local/Docker backend with the ML dependencies. An API-only
Vercel function can serve the dashboard/data but **cannot run this camera/ML
worker**. Playback and detection are separate capabilities.

```bash
cd TRINETRAAI/backend
pip install -r requirements-ml.txt
python ../../scripts/ensure_headless_opencv.py
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

# Another terminal, from the repository root:
cd trinetra-ai
npm ci
VITE_USE_MOCKS=false npm run dev
```

In your untracked backend `.env`, use the live settings below. Configure only
streams you are authorized to access. Keep stream credentials in the backend /
server-side proxy configuration, not `VITE_` variables or source control.

```dotenv
DEMO_MODE=false
DEMO_ALERTS_ENABLED=false
LIVE_ANPR_ENABLED=true
LIVE_ANPR_MAX_VEHICLES=3
LIVE_ANPR_SAMPLE_SECONDS=1
LIVE_ANPR_WORKERS=1
CV_CPU_THREADS=2
LIVE_ANPR_DEDUP_SECONDS=60
OCR_ENABLED=true
```

Open **Live Cameras → Open camera**. **Plate detection: On** is the default.
The player shows boxes and readable numbers; the camera's history and
**Vehicle Log** refresh automatically. Ordinary plate reads generate an
**in-app notification**, with a link to that plate/camera in the log. They do
not become police/watchlist alarms merely because a plate was read.

- Sentinel WHEP/HLS stays on native browser playback. A high-quality JPEG
  sample (maximum 1280px) is submitted about once per second. No video upload
  or extra RTSP connection is necessary for this path.
- File cameras and other authorized RTSP/HLS cameras use the same-origin
  backend MJPEG view. Inference runs separately from decoding/rendering.
- Browser sampling runs only while its player is playing in a visible tab.
  To keep scanning after navigating away, start the camera's **resident
  backend ingestion** (`POST /api/cameras/CAMERA_ID/start`). It must be
  reachable from the backend. `AUTO_START_CAMERAS=true` starts configured
  network cameras at boot; do not enable a whole large grid on a small CPU.
  Stop a resident worker with `POST /api/cameras/CAMERA_ID/stop`.
- **Recorded footage is labelled RECORDED, not LIVE.** Its log records carry
  the filename and video offset. `event_time` is the time the sample was
  processed/captured during playback, not a recovered original recording date.
- Notifications are in-app, not SMS or operating-system push notifications.

## Photo evidence — direct from detections

**Photo evidence** sits beside the player on desktop and directly below it on
mobile. It automatically shows the latest detected vehicle crops (up to the
configured vehicle budget), **before OCR or two-read agreement**. A vehicle
whose plate is unreadable still gets its real photo, labelled **Plate not read**.
No stock photo is substituted when a real image cannot be loaded.

- The gallery follows new captures without a refresh or table selection.
  Selecting **View** in the history pins that saved event for review;
  **Follow latest** resumes the automatic gallery.
- Preview images use unique capture IDs, original observation timestamps and
  recording offsets. They are not a second live video or invented log entries.
- `GET /api/cameras/{id}/anpr` (and browser frame responses) includes `photos`.
  Image paths resolve under the configured API origin/version prefix, including
  `/api/v1`. The new photo endpoint serves JPEG bytes without running inference.
- Preview storage is memory-only: **30 seconds, at most 64 capture batches / 16 MB
  globally**. It does not write every frame to disk or create unknown-plate log
  records. Readable, agreed plate sightings still retain their normal saved
  evidence in the Vehicle Log. Preview photos are not archival evidence.
- Saved evidence shows the whole crop (`object-contain`), supports retries, and
  retries a new URL automatically even if the previous capture failed to load.

## Detection integrity

- Nothing is generated to fill an empty log. No read → `UNKNOWN` in the
  overlay, no invented plate record/notification.
- At least two agreeing reads on a track are required before writing a plate.
  Frozen browser frames cannot count twice. Reconnects, loops, resolution
  changes and long sampling gaps reset tracking/votes. A continuing vehicle
  box cannot indefinitely preserve an unreadable plate: without a fresh OCR
  read, its identity expires after `max(5s, 3 × sample interval)` and must
  agree again. This is separate from the shorter stale-frame overlay TTL.
- A tiny 16×9 luminance sketch also suppresses cached boxes on visibly changed
  pictures and resets votes on detected scene cuts. It is a conservative,
  inexpensive guard, not a guarantee of perfect tracking or a second detector.
- `HIGH` requires the existing confidence threshold (default 0.80), agreement
  and the canonical Indian format. Plausible lower-confidence reads are saved
  as `LOW_CONFIDENCE`, shown as **Verify read**, and cannot raise a watchlist
  alert. An OCR confidence score is not a guarantee of correctness.
- Two-/three-line motorcycle plates can be joined **within a localized plate
  region only**, using the weakest line's confidence, not an inflated score.
- The configured site-trained plate model takes priority. Otherwise the
  bundled `trinetra_detection/models/best.pt` supplies its **number_plate**
  class (never its vehicle class). Classical proposals remain a fallback.
  Set `PLATE_MODEL_PATH=` to explicitly use classical proposals only.
- Each persisted sighting includes camera, timestamp, normalized/raw plate,
  confidence/tier, vehicle class/box, and a real vehicle crop when storage is
  writable. Plate crops are saved when localization supplied a plate box.
- One sighting per continuous track/plate. The camera+plate sliding cooldown
  (default 60s) suppresses duplicates across nearby tracks/viewers/reconnects.
  Another camera may log the same plate independently. A later revisit may
  generate another sighting. The DB is also checked after a service restart.
- Live SSE failures show OFFLINE and reconnect; they do **not** start a mock
  alert rotation. Scripted backend alerts require both `DEMO_MODE=true` and
  `DEMO_ALERTS_ENABLED=true`. Synthetic camera fallback frames are excluded
  from this ANPR pipeline even in demo mode.

## Smoothness and capacity

Playback does not wait for OCR. Each camera has **one replaceable pending
frame**; old samples are dropped instead of building latency. The worker pool,
active camera states and native CPU thread pools are bounded. A busy camera
cannot move other cameras to the back of the processing queue. Confirmed
numbers stay visible during short OCR rechecks rather than flickering back to
“reading plate”. A contradictory read clears the old number immediately.
A temporary background refresh failure keeps the last successful Vehicle Log
rows on screen; a successful retry reconciles them without a full-page reload.

| Setting | Default | Purpose |
|---|---:|---|
| `LIVE_ANPR_MAX_VEHICLES` | 3 | Largest vehicle boxes considered per sampled frame |
| `LIVE_ANPR_SAMPLE_SECONDS` | 1 | Minimum sampling interval per camera |
| `LIVE_ANPR_WORKERS` | 1 | Shared inference workers, not one worker per viewer |
| `CV_CPU_THREADS` | 2 | Native YOLO/OCR CPU thread budget |
| `LIVE_ANPR_MAX_CAMERAS` | 32 | Memory/admission limit, **not** a throughput guarantee |
| `LIVE_ANPR_DEDUP_SECONDS` | 60 | Repeat-sighting cooldown |
| `LIVE_ANPR_OVERLAY_TTL_SECONDS` | 3 | Hide boxes from old source frames |
| `LIVE_ANPR_IDLE_SECONDS` | 60 | Release idle camera state |

RapidOCR processes plate-sized images with a **maximum** detector dimension
of 640. Its previous default enlarged the *minimum* side of every crop to
736, wasting CPU on multi-megapixel inputs. Small plates are still upscaled
before recognition, rather than throwing away their text detail.

Start with a few simultaneous feeds and measure on your machine. Two–three
vehicles per sample is a processing budget, **not a promise that every feed
contains two–three readable plates**. Tiny, occluded, blurred or overexposed
plates may be unreadable; skipped vehicles can pass between samples. For
many cameras, use appropriate compute/edge workers and tune the budget.

Run one ASGI process for this in-memory scheduler. Multiple independent API
processes would need shared scheduling/deduplication before making exactly-once
claims. Keep the API behind your trusted/authenticated deployment boundary;
this feature is not an authentication or retention-policy implementation.

## API and verification

- `POST /api/cameras/{id}/detect-frame`: `image/jpeg`, maximum 2 MB / 1920²
  pixels; optional `client_id` and monotonic `media_time`. Returns admission
  status and the most recent fresh result, **not a blocking inference job**.
- `GET /api/cameras/{id}/anpr`: status, frame dimensions, result age, sampled
  boxes/plates and their event IDs. No fabricated result on missing models.
- Existing `/api/events`, `/api/stream`, `/api/ws/events` and evidence endpoints
  carry the persisted sightings. `/api/v1` aliases remain available.

```bash
.venv/bin/python -m pytest TRINETRAAI/backend/tests -q
npm --prefix trinetra-ai test
npm --prefix trinetra-ai run build
# Optional actual YOLO smoke test with installed ML dependencies:
.venv/bin/python -m pytest TRINETRAAI/backend/tests/test_vehicle_detection.py -m slow -q
```

The live integration tests use controlled detector/OCR fixtures to verify
three-vehicle handling, storage, evidence, SSE delivery, notification dedup,
camera isolation, capacity, stale overlays, failures and lifecycle. They are
**not accuracy benchmarks**. Real model smoke checks use the repository's
recording/sample images only; final plate accuracy, end-to-end delay and smooth
multi-camera playback must be validated on the operator's own authorized feeds.


### Repeatable browser smoke (optional)

`scripts/verify/live_anpr_browser.py` opens a **registered FILE camera**, waits
for a real model/OCR notification, and checks:

1. A new persisted event with recording filename/offset (not a seeded event).
2. The same event/plate in the camera's overlay snapshot.
3. Automatic insertion into a Vehicle Log that was open before playback.
4. The notification action updates the filters even when already on that page.
5. Its real evidence crop is served and there are no browser JavaScript errors.

Use a **disposable database and evidence directory**, not production data. One
way to register the bundled file for this test is to set these on your test
backend before starting it (expand the absolute repository path locally):

```dotenv
DATABASE_URL=sqlite:////ABSOLUTE/REPO/.cache/anpr-smoke.db
EVIDENCE_ROOT=/ABSOLUTE/REPO/.cache/anpr-smoke-evidence
LIVE_CAMERA_ID=RECORDED
LIVE_CAMERA_NAME=Recorded smoke fixture - not live
LIVE_CAMERA_STREAM_TYPE=file
LIVE_CAMERA_STREAM_URL=/ABSOLUTE/REPO/TRINETRAAI/backend/demo_cam04.mp4
DEMO_MODE=false
DEMO_ALERTS_ENABLED=false
AUTO_START_CAMERAS=false
```

With that backend and the real-mode frontend running:

```bash
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/verify/live_anpr_browser.py \
  --app-url http://127.0.0.1:5173 --camera-id recorded
```

To check the immediate photo gallery without requiring a readable plate or
waiting for a notification, add `--photos-only`. This verifies loaded vehicle
images and automatic capture updates using the real model, without selecting
an existing Vehicle Log entry. Add `--mobile` to check the 390px layout.
Optionally pass `--empty-camera-id CAMLIVE` to verify that switching to an
**unconfigured** registry slot with no saved events clears the previous camera's
photos and that returning resumes the gallery, without a page reload. The script refuses this
switch check if that slot has a source, so it cannot accidentally open another
live feed.

`--chromium-binary /path/to/chromium` supports an existing Chromium install.
The script writes its JSON report and screenshots into the ignored
`.cache/live-anpr-browser/` directory. It only opens playback: it never sends
an invented event/OCR answer, weakens thresholds, disables deduplication, or
deletes stored sightings. Use fresh test data (or wait out the cooldown with
playback stopped) before repeating; an already-reported plate is deliberately
not notified again. Unreadable or watchlisted-only footage will not produce
the ordinary notification this smoke expects.

The bundled **demo fixture** alternates three sample photographs at 12 fps;
it is not a continuous recording of traffic. The browser check has exercised
both the ordinary and **Verify read** paths with actual models, including persistence, SSE, overlay,
auto-refresh, same-route notification navigation and evidence delivery. This
is a functional check on that fixture, not a claim of general OCR accuracy or
smooth multi-camera performance on an operator's real feeds. Its rapid image
changes also exercise hiding asynchronous boxes belonging to a different scene.


## Optional traffic observations

The same detector also supports motion-aware tracking and per-camera normalized
line/zone counts; see [Traffic counting](TRAFFIC_COUNTING.md). Counting has a
separate bounded tracking budget and does not increase the OCR/photo budget.
Plate sightings and observation-session counters are deliberately separate.

## A visible plate still says unreadable

A vehicle photo is published **before** OCR completes. The photo panel now
separates **Waiting for OCR**, **Reading plate**, **Confirming (1/2 samples)**,
low confidence, missing/tiny regions and engine failures. Only a confirmed
identity gets a plate number/event; the absence of a number is not necessarily
a finished failed read. Each vehicle's completed status is published without
waiting for the other vehicles in the batch.

**Show area scanned for text** displays the actual OCR search crop, including
failed attempts. It is labelled as a proposed/search area, not guaranteed plate
localization. `/api/health` also exposes cached `ocr` engine state without
loading a model just because health was polled.

Localized plate crops have modest clipped padding while preserving the original
character scale. If localization picked an unhelpful region and OCR yielded no
valid read, one lower-vehicle rescue region gets at most two extra OCR attempts.
The per-vehicle budget is at most eight OCR calls (two localized regions × three
variants, plus two rescue calls). No extra vehicle detector call is added.
Rescue accepts only canonical text actually returned by OCR, never joins strings
across a whole vehicle, never replaces uncertain letters/digits to force a match,
and remains **Verify read** even with high OCR confidence. Two independently
sampled agreeing reads and the existing rejection threshold still apply; rescue
reads cannot trigger watchlist alarms.

Resizing is interpolation, not recovery of missing detail. A screenshot of a
thumbnail cannot establish the engine's original input quality or output.
Exact false negatives need the original captured photo/video plus camera/sample
context. Repository crop checks are integration checks, not a claim that the
operator's specific plate has been recognized correctly.
