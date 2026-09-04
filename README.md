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
| **LIVE** | `VITE_USE_MOCKS=false VITE_BACKEND_ORIGIN=http://localhost:8000 npm run dev` | Real backend only — real events, alerts, SSE realtime, GIS routes. No synthetic plates/confidences/routes |

Run the backend with `DEMO_MODE=false` in LIVE mode so unreachable cameras stay
honestly `OFFLINE` instead of falling back to the backend's synthetic feed.

## Tests

```bash
cd TRINETRAAI/backend && pytest          # 97 tests
cd cv-engine && pytest                   # 79 offline tests (live-feed tests opt-in)
cd cv-engine && TRINETRA_LIVE=1 pytest -m live tests/test_live_sentinel.py -v
```
