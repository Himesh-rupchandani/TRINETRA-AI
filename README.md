# TRINETRA AI — Intelligent Vision. Faster Response.

Hybrid CCTV intelligence platform for the Gujarat Police Innovation Hackathon.

| Component | Path | Role |
|---|---|---|
| **cv-engine** | [`cv-engine/`](cv-engine/README.md) | AI/CV pipeline: Sentinel feed → YOLO11 detection → PTS-driven tracking → ANPR → sighting events (`POST /api/events`) |
| Backend | `TRINETRAAI/backend/` | FastAPI: event ingestion, watchlist matching, alert dedup, GIS vehicle routes, Sentinel catalogue sync, WebSocket realtime |
| Frontend | `trinetra-ai/` | Dashboard, camera grid, investigation & GIS views |

## The flow

```
Sentinel CCTV → Frame (PTS) → Vehicle Detection (YOLO11) → Tracking
→ ANPR/OCR → Event JSON → POST /api/events → Watchlist → 🚨 Alert
→ Frontend → Vehicle Search → GIS Route
```

## Quick start

```bash
# Backend (port 8000)
cd TRINETRAAI/backend && pip install -r requirements.txt
python -m scripts.seed_demo
# Point every registry camera at a local traffic clip (offline demo) —
# video is then decoded ON DEMAND when an operator opens a camera:
python -m scripts.point_cameras_at_local_feeds   # cycles 12 REAL traffic clips
# (highway CCTV, city CCTV, 2 intersection cams, crosswalk w/ pedestrians,
#  night traffic, aerial highway, and a small CCTV clip — see the script)
# EVIDENCE_ROOT serves the CV engine's detection crops at /api/evidence/...
EVIDENCE_ROOT=../../cv-engine/evidence uvicorn app.main:app --host 0.0.0.0 --port 8000
# (AUTO_START_CAMERAS=true is only for REAL RTSP/HLS deployments — it starts
# a resident ingest worker per camera. Do NOT enable it with 32 file cameras
# on a small machine.)

# CV engine — real Sentinel camera (live mode)
cd cv-engine && pip install -r requirements.txt
python scripts/fetch_models.py          # one-time model download
python scripts/run_pipeline.py --mode live --camera cam04

# CV engine — offline demo mode (scripted fixtures, clearly NOT live)
python scripts/run_pipeline.py --mode demo
```

## CV engine — local feed demo (REAL detection, no Sentinel network needed)

Two clearly-labelled `DEMO FEED` cameras run the **real** pipeline — YOLO11
detection → ByteTrack tracking → sighting events → backend → dashboard/SSE —
on local traffic videos, and stream an **annotated live view** (bounding boxes
+ track IDs) the browser plays directly:

```bash
# 1. one-time: put traffic videos in cv-engine/feeds/ and the model in cv-engine/models/
#    (los_angeles.mp4, cctv.avi — any traffic clip works; yolo11n.pt)
# 2. register the demo-feed cameras in the backend registry (stream_type='file')
cd TRINETRAAI/backend && python - << 'PY'
from app.database.database import SessionLocal
from app.database.models import Camera
db = SessionLocal()
if not db.query(Camera).filter(Camera.camera_id == 'CAMD01').first():
    db.add(Camera(camera_id='CAMD01', name='DEMO FEED — Highway Interchange', location='Local Demo Interchange',
                  stream_url='<abs path>/cv-engine/feeds/los_angeles.mp4', stream_type='file',
                  latitude=23.0322, longitude=72.5570, status='ONLINE'))
    db.commit()
PY
# 3. restart the backend (it opens file sources like any camera), then:
cd cv-engine && pip install -r requirements.txt   # incl. torch CPU + ultralytics
python scripts/run_feed_demo.py                   # detection + events + annotated MJPEG on :8555
```

The frontend picks the annotated view automatically (`/cvfeed/<id>`, proxied),
falling back to the backend's own MJPEG mirror when the CV engine is off.
Every frame is watermarked **LOCAL DEMO FEED** — never mistaken for Sentinel.

Every emitted event also stores a **cropped vehicle photo** (evidence) under
`cv-engine/evidence/<camera>/`, which the backend serves at
`/api/evidence/<ref>` — the Events page shows the crop plus full details
(class, track ID, camera, GPS, timestamps) in its evidence drawer.

## Official Sentinel Camera Grid integration

In real mode, when approved server-side credentials are present, the backend
synchronizes the official catalogue (`https://cctv.corp8.cloud/cameras.json`)
at startup (`SENTINEL_AUTO_SYNC=true`). It can also be refreshed through
`POST /api/internal/sentinel/catalogue/sync`. Camera IDs are NEVER hard-coded;
names, locations, and coordinates come from the authorized payload and are
normalized into the internal registry. A fresh live database is intentionally
left empty if that authorized sync cannot be reached rather than showing demo
placeholder cameras as official feeds.

**Primary credentials live in `TRINETRAAI/backend/.env`** (gitignored; see
`.env.example` for placeholders). The cv-engine shell and the frontend dev
proxy need their own server-side copies — see "Running the real Sentinel grid"
below. Credentials never reach the browser or the database:

```env
SENTINEL_EMAIL=you@example.com     # '@' is auto-encoded as %40 in URLs
SENTINEL_PASSWORD=changeme
SENTINEL_CATALOGUE_URL=https://cctv.corp8.cloud/cameras.json
SENTINEL_HLS_BASE_URL=https://cctv.corp8.cloud
SENTINEL_RTSP_HOST=103.250.160.189
SENTINEL_RTSP_PORT=8554
```

Flow (all URLs with credentials are built at connect time, backend-only,
never stored in the DB, never returned by any API, never logged unredacted):

- **AI ingestion**: `POST /api/cameras/cam04/start` resolves the
  authenticated RTSP URL (TCP transport forced, reconnect 2s→30s backoff)
  and feeds the existing YOLO11 → ByteTrack → ANPR → events pipeline.
- **Browser viewing**: HLS/WHEP through same-origin paths only
  (`/api/cameras/{id}/live`, `/sentinel/stream/{id}/whep` via the dev
  proxy, which injects the Sentinel credentials as HTTP Basic auth —
  see `trinetra-ai/.env.local.example`). The frontend never sees a credential.
- **CV engine live mode**: `python scripts/run_pipeline.py --mode live
  --camera cam04` — synthesizes the same authenticated RTSP URL from env
  when the catalogue lists only camera IDs.

### Windows — open the local configuration in Notepad

On the approved Windows machine, run this from the repository root (for
example `C:\Users\Lenovo\hack`):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\configure-official-camera.ps1
```

The helper creates only the Git-ignored local files
`TRINETRAAI\backend\.env` and `trinetra-ai\.env.local`, then opens each in
Notepad. Enter the registered **official email** and **access password** only
there; never paste them into chat, source code, a `VITE_` variable, Git, or a
browser form. It also sets `DEMO_MODE=false` for a newly created backend file,
so an unavailable official feed is reported as unavailable rather than replaced
with a synthetic feed. It does not grant access or test credentials: the account
and network must already be authorized by the camera operator.

After saving and closing both Notepad windows, use the two command sequences
printed by the helper (backend first, then frontend). The frontend's local
`BACKEND_ORIGIN` makes its same-origin `/api` proxy point at the local backend.

### Running the real Sentinel grid (start here on demo day)

The code is split into three processes; each needs the Sentinel credentials
somewhere **server-side**. Put your registered email + access password in:

1. `TRINETRAAI/backend/.env` → backend AI ingestion + browser tickets
   (`cp .env.example .env` and fill in `SENTINEL_EMAIL` / `SENTINEL_PASSWORD`).
2. Your shell, for cv-engine live mode (no .env auto-load there):
   `export SENTINEL_EMAIL=... SENTINEL_PASSWORD=...` (`@` may be plain; it is
   percent-encoded as `%40` when the RTSP URL is built).
3. `trinetra-ai/.env.local` (ignored by Git; server-side only, **no `VITE_`
   prefix**) → the dev-server proxy uses it to authenticate every WHEP
   connection to the gateway (`SENTINEL_EMAIL` / `SENTINEL_PASSWORD`; copy the
   names from `.env.local.example`).

Then, in three terminals:

```bash
# 1. Backend — seeded demo registry (30 Sentinel cameras), API on :8000
cd TRINETRAAI/backend && python -m scripts.seed_demo
EVIDENCE_ROOT=../../cv-engine/evidence uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. AI pipeline on one real camera (needs exports above + venue network)
cd cv-engine && python scripts/run_pipeline.py --mode live --camera cam04 --duration 300

# 3. Control room — LIVE mode against the real backend
cd trinetra-ai && VITE_USE_MOCKS=false BACKEND_ORIGIN=http://localhost:8000 npm run dev
```

Common errors, decoded:

| Symptom | Cause → fix |
|---|---|
| `curl https://cctv.corp8.cloud/cameras.json` → HTTP 000 / SSL error | You are not on a network that can reach the CDN host (Cloudflare-fronted). The grid is reachable from the venue/allowed network — not from every sandbox/office network. |
| RTSP/WHEP `401 Unauthorized` | Credentials missing or not on the approved access list. Check `SENTINEL_EMAIL`/`SENTINEL_PASSWORD` in the right place (backend `.env`, shell for cv-engine, `trinetra-ai/.env.local` for the browser proxy). Email `@` must belong to an approved account. |
| WHEP player: "Camera path is not published on the gateway" | A stale ticket path. The backend ticket is `/sentinel/stream/<id>/whep` (matches gateway `/stream/<id>/whep` behind the proxy). Rebuilt frontends/tickets use this; any `/sentinel/<id>/whep`-style URL is the old bug. |
| `ImportError: libGL.so.1: cannot open shared object file` (cv2) | GUI `opencv-python` (pulled by ultralytics/rapidocr) overwrote the headless build → `pip uninstall -y opencv-python && pip install -q opencv-python-headless`. |
| Cameras never go ONLINE in LIVE mode | `AUTO_START_CAMERAS=false` (default) means nothing connects at boot. Either call `POST /api/cameras/{id}/start` per camera you process, or set `AUTO_START_CAMERAS=true` on a machine that can actually reach the grid. |
| YOLO/ANPR missing at runtime | `python scripts/fetch_models.py` (weights) was never run, or tesseract isn't installed — cv-engine uses `rapidocr-onnxruntime` (bundled) for OCR. |

## Connecting a REAL live camera (e.g. authorized Ahmedabad CCTV)

No authorized public Ahmedabad CCTV feed exists today — the city's ANPR/CCTV
network feeds government control rooms only. The system therefore ships with
an env-configured live-camera slot that stays honestly **NOT_CONFIGURED**
("Camera source not configured") until you add an authorized URL. Recorded
demo clips are always stamped `RECORDED DEMO FOOTAGE — NOT LIVE` and are
never labelled live.

When you receive an authorized stream URL, edit `TRINETRAAI/backend/.env`
(see `.env.example`) — no code changes, just restart the backend:

```env
LIVE_CAMERA_NAME=SG Highway Junction, Ahmedabad
LIVE_CAMERA_LOCATION=Ahmedabad, Gujarat
LIVE_CAMERA_STREAM_TYPE=rtsp          # rtsp | hls | webrtc | whep | file
LIVE_CAMERA_STREAM_URL=rtsp://...     # authorized URL, local .env only
# For a WHEP/WebRTC viewing feed, supply the authorized server-side source
# OpenCV will decode (WHEP itself is browser signalling, not an OpenCV input):
LIVE_CAMERA_INGEST_URL=rtsp://...
LIVE_CAMERA_INGEST_TYPE=rtsp
AUTO_START_CAMERAS=true               # connect real network cameras at boot
```

The raw authorized URL never enters the database, API response, browser,
source control, or logs: only a credential-free reference is registered and
the backend resolves the environment value immediately before connection.
For an existing Sentinel camera, the backend synthesizes the authenticated
RTSP URL from `SENTINEL_EMAIL` / `SENTINEL_PASSWORD` at the same point.

`/api/cameras/{id}/live/detect` now uses vehicle-only YOLO inference with
class-aware NMS, conservative cross-pass de-duplication, and PTS-driven
multi-object tracking. It draws one stable green box per detected car,
motorcycle, bus, truck, and (by default) bicycle; lower-confidence partial
occlusions may maintain an existing track but cannot instantly become a false
new box. The default 960px detector input improves distant-road-vehicle recall.
Set `DETECTION_TILE_GRID=2` on suitable GPU hardware when maximum dense,
far-vehicle recall matters more than throughput; leave it at `1` for the
normal real-time path.

Statuses are always honest: **Working** only while frames actually arrive
from the real camera; **Not working** when the stream is unreachable;
**NOT_CONFIGURED** when no source is set. Resident workers start only for
real network cameras — the file-backed demo grid always plays on demand.

## Frontend modes

| Mode | How | Data source |
|---|---|---|
| **DEMO** (repo default) | `VITE_USE_MOCKS=true` | In-browser synthetic dataset incl. the scripted `GJ01AB1234` journey |
| **LIVE** | `VITE_USE_MOCKS=false BACKEND_ORIGIN=http://localhost:8000 npm run dev` | Real backend only — real events, alerts, SSE realtime, GIS routes. No synthetic plates/confidences/routes |

Run the backend with `DEMO_MODE=false` in LIVE mode so unreachable cameras stay
honestly `OFFLINE` instead of falling back to the backend's synthetic feed.

## Tests

```bash
cd TRINETRAAI/backend && pytest          # 112 tests
cd cv-engine && pytest                   # 80 offline tests (live-feed tests opt-in)
cd cv-engine && TRINETRA_LIVE=1 pytest -m live tests/test_live_sentinel.py -v
```
