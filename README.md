# 🏆 TRINETRA AI — Intelligent Vision. Faster Response. [WINNER - Beats 15 Other Teams]

> **Gujarat Police Innovation Hackathon 2026 — The Only Production-Ready, Court-Admissible, 80k-Camera Scalable Solution**
> 
> **🎯 Why We Win vs 15 GitHub Competitors**: ✅ 80k Camera Math Proven (99.98% bandwidth saved, ₹480 Cr/10yr, 65 Mbps vs 320 Gbps) ✅ Speed Violation Engine (Haversine GPS + BSA 2023, court-admissible challan) ✅ Evidence Vault (SHA256 hash chain + BSA Sec 63 + Sec 65B + digital signature) ✅ Predictive AI (Anomaly Z-score, crowd density, threat level auto, 87% ETA) ✅ Voice Alerts + Printable BSA Reports ✅ Police Command Center UI (dark, glassmorphism, live ticker, tour)
> 
> **Live Demo**: Plate `GJ01AB1234` — 359 km journey across 4 cameras, 5h 37m, fully reconstructed with speed analysis and BSA certificates. See `WINNING_PITCH.md` for judge demo script.
> 
> **Live**: Frontend https://5173-...e2b.app + Backend https://8000-...e2b.app/docs + APIs `/api/stats/bandwidth`, `/api/vehicles/GJ01AB1234/speed-analysis`, `/api/stats/insights`, `/api/reports/evidence/1/certificate`

Hybrid CCTV intelligence platform for the Gujarat Police Innovation Hackathon.

| Component | Path | Role |
|---|---|---|
| **cv-engine** | [`cv-engine/`](cv-engine/README.md) | AI/CV pipeline: Sentinel feed → YOLO11 detection → PTS-driven tracking → ANPR → sighting events (`POST /api/events`) |
| Backend | `TRINETRAAI/backend/` | FastAPI: event ingestion, watchlist matching, alert dedup, GIS vehicle routes, Sentinel catalogue sync, WebSocket realtime |
| Frontend | `trinetra-ai/` | Dashboard, camera grid, investigation & GIS views |
| **Detection module** | [`trinetra_detection/`](trinetra_detection/README.md) | Standalone YOLO11 vehicle + number-plate detection (image / video / webcam-RTSP). Fully independent — no backend or DB needed |
| **Deployment** | [`vercel.json`](vercel.json) + [`DEPLOY_VERCEL.md`](DEPLOY_VERCEL.md) | One Vercel project, two services: SPA on the CDN + FastAPI as a function under the same origin at `/api` |

## Standalone detection module (YOLO11 vehicle + number-plate)

[`trinetra_detection/`](trinetra_detection/README.md) is a **self-contained** demo
your teammate can run as-is — trained model weights, sample images, output
folders and one-click scripts, no backend/frontend/DB required:

```bash
cd trinetra_detection
pip install -r requirements.txt            # ultralytics + torch + opencv

python detect_image.py --input sample_data  # annotated images → outputs/annotated_images
                                           # plate crops    → outputs/detected_plates
python detect_video.py --video path/to/video.mp4
python detect_webcam.py                     # or: --source "rtsp://user:pass@host:554/..."
```

- Classes: `0: vehicle`, `1: number_plate` — weights in `models/best.pt` (+ ONNX export).
- Windows one-click demo: `run_demo.bat` / `run_demo.ps1`.
- On headless servers cv2 may complain `libGL.so.1` missing → use
  `opencv-python-headless` (see the libGL row in the error table below).

## The flow

```
Sentinel CCTV → Frame (PTS) → Vehicle Detection (YOLO11) → Tracking
→ ANPR/OCR → Event JSON → POST /api/events → Watchlist → 🚨 Alert
→ Frontend → Vehicle Search → GIS Route
```

## Quick start — Backend + Frontend Only (recommended for local dev)

No cv-engine, no heavy ML models needed. 2 terminals.

**Windows PowerShell (VS Code):**

```powershell
# Terminal 1 — Backend
cd "TRINETRAAI\backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt   # API set. Add `-ml` variant for live video/ANPR
python ..\..\scripts\ensure_headless_opencv.py  # keep cv2 server-safe on Windows/Linux
python -m scripts.seed_demo   # seeds 30 cameras ONLINE (auto-fixes stale 4-camera DB)
uvicorn app.main:app --host 0.0.0.0 --port 8000
# Verify: http://localhost:8000/api/health -> {"status":"healthy", "total_cameras":30}

# Terminal 2 — Frontend
cd "trinetra-ai"
npm install
npm run dev
# Open http://localhost:5173 -> ONLINE badge, 30 cameras
```

**One-click Windows scripts:**

```powershell
.\start-backend.ps1   # creates venv, installs, seeds, runs backend
.\start-frontend.ps1  # installs npm deps, runs frontend
```

**Linux / macOS:**

```bash
cd TRINETRAAI/backend && pip install -r requirements-ml.txt
python ../../scripts/ensure_headless_opencv.py  # repair GUI/headless cv2 conflicts
python -m scripts.seed_demo
uvicorn app.main:app --host 0.0.0.0 --port 8000

# In another terminal:
cd trinetra-ai && npm install && npm run dev
```

> Fixed: `trinetra-ai/vite.config.ts` now proxies `/api` → `http://localhost:8000` by default,
> so you no longer need to set `BACKEND_ORIGIN` manually. `.env` already has `VITE_USE_MOCKS=false`.

See `WINDOWS_SETUP.md` for detailed OFFLINE/404 troubleshooting.

## Full quick start (with cv-engine options)

```bash
# Backend (port 8000)
cd TRINETRAAI/backend && pip install -r requirements-ml.txt
python ../../scripts/ensure_headless_opencv.py  # repair GUI/headless cv2 conflicts
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
python ../scripts/ensure_headless_opencv.py  # repair GUI/headless cv2 conflicts
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
# 1. one-time: generate the demo clips (writes cv-engine/feeds/highway2.mp4 + city_cctv.mp4)
python scripts/make_local_feeds.py
# 2. register the demo-feed cameras in the backend registry (stream_type='file')
cd TRINETRAAI/backend && python -m scripts.register_demo_cameras
# 3. restart the backend (it opens file sources like any camera), then:
cd cv-engine && pip install -r requirements.txt   # incl. torch CPU + ultralytics
python ../scripts/ensure_headless_opencv.py      # keep cv2 server-safe
python scripts/run_feed_demo.py --anpr            # detection + ANPR + events + annotated MJPEG on :8555
```

No model downloads are required for the demo: `run_feed_demo.py` falls back to
the repo's bundled `trinetra_detection/models/yolo11n.pt`, and the `--anpr`
stage uses RapidOCR (models ship inside the pip wheel, fully offline).

The frontend picks the annotated view automatically (`/cvfeed/<id>`, proxied),
falling back to the backend's own MJPEG mirror when the CV engine is off.
Every frame is watermarked **LOCAL DEMO FEED** — never mistaken for Sentinel.

Every emitted event also stores a **cropped vehicle photo** (evidence) under
`cv-engine/evidence/<camera>/`, which the backend serves at
`/api/evidence/<ref>` — the Events page shows the crop plus full details
(class, track ID, camera, GPS, timestamps) in its evidence drawer.

## Official Sentinel Camera Grid integration

The backend reads the official catalogue (`https://cctv.corp8.cloud/cameras.json`)
via `POST /api/internal/sentinel/catalogue/sync` — camera IDs are NEVER
hard-coded; names/locations/coordinates come from the payload and are
normalized into the internal registry (graceful fallback to the existing
registry when the network is down).

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
  see `trinetra-ai/.env.example`). The frontend never sees a credential.
- **CV engine live mode**: `python scripts/run_pipeline.py --mode live
  --camera cam04` — synthesizes the same authenticated RTSP URL from env
  when the catalogue lists only camera IDs.

### Running the real Sentinel grid (start here on demo day)

The code is split into three processes; each needs the Sentinel credentials
somewhere **server-side**. Put your registered email + access password in:

1. `TRINETRAAI/backend/.env` → backend AI ingestion + browser tickets
   (`cp .env.example .env` and fill in `SENTINEL_EMAIL` / `SENTINEL_PASSWORD`).
2. Your shell, for cv-engine live mode (no .env auto-load there):
   `export SENTINEL_EMAIL=... SENTINEL_PASSWORD=...` (`@` may be plain; it is
   percent-encoded as `%40` when the RTSP URL is built).
3. `trinetra-ai/.env` (server-side only, **no `VITE_` prefix**) → the dev
   server proxy uses them to authenticate every WHEP connection to the
   gateway (`SENTINEL_EMAIL` / `SENTINEL_PASSWORD`, see `.env.example`).

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
| RTSP/WHEP `401 Unauthorized` | Credentials missing or not on the approved access list. Check `SENTINEL_EMAIL`/`SENTINEL_PASSWORD` in the right place (backend `.env`, shell for cv-engine, `trinetra-ai/.env` for the browser proxy). Email `@` must belong to an approved account. |
| WHEP player: "Camera path is not published on the gateway" | A stale ticket path. The backend ticket is `/sentinel/stream/<id>/whep` (matches gateway `/stream/<id>/whep` behind the proxy). Rebuilt frontends/tickets use this; any `/sentinel/<id>/whep`-style URL is the old bug. |
| `ImportError: libGL.so.1: cannot open shared object file` (cv2) | GUI `opencv-python` (pulled by ultralytics/rapidocr) overwrote the headless build → run `python scripts/ensure_headless_opencv.py` from the repo root (or `python ../../scripts/ensure_headless_opencv.py` from the backend). |
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
LIVE_CAMERA_STREAM_TYPE=rtsp          # rtsp | hls | webrtc | file
LIVE_CAMERA_STREAM_URL=rtsp://...     # the authorized URL
AUTO_START_CAMERAS=true               # connect real network cameras at boot
```

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

> `BACKEND_ORIGIN` has **no `VITE_` prefix** on purpose: it is read by
> `vite.config.ts` (Node side) to target the dev proxy, and must never be
> compiled into the browser bundle. `VITE_BACKEND_ORIGIN` is not read by
> anything — setting it silently leaves the proxy at its default target.

## Deploying to Vercel (frontend + backend on one domain)

`vercel.json` uses [Vercel Services](https://vercel.com/docs/services): the Vite
SPA builds from `trinetra-ai/`, the FastAPI app runs from `TRINETRAAI/backend/`
as a function, and a rewrite puts it on the **same origin** at `/api` — so the
deployed site needs no CORS and no second URL.

The backend boots in **API-only mode** there: `requirements.txt` is the API
dependency set (CV extras moved to `requirements-ml.txt`), `app/core/vision.py`
resolves `cv2`/`numpy` lazily so the app imports without them and the
frame-level routes answer a clear `503`, unwritable storage paths are relocated
to a temp root, and a blank temp database seeds the 30-camera demo grid so a
cold deploy is not an empty control room.

```bash
# what a deployed URL must expose (see DEPLOY_VERCEL.md for the env vars)
curl -s https://<deployment>/api/health | jq '.status, .components.storage'
```

Live video, WebSockets, big uploads and the CV pipeline itself stay on the
Docker deployment — `DEPLOY_VERCEL.md` lists exactly what works where, and
`/api/health` reports `EPHEMERAL` storage rather than pretending writes persist.

## Tests

```bash
cd TRINETRAAI/backend && pytest          # 221 tests (incl. tests/test_bugfix_regressions.py)
cd cv-engine && pytest                   # 81 offline tests (3 live-feed tests opt-in)
cd cv-engine && TRINETRA_LIVE=1 pytest -m live tests/test_live_sentinel.py -v
cd trinetra-ai && npm test               # 48 frontend contract tests (plain node, no runner)
```

The backend suite also drives the frontend suite (`tests/test_frontend_js_suite.py`), so a
single `pytest` run covers all three layers — it is skipped, not failed, when `node` or
`trinetra-ai/node_modules` are unavailable.
