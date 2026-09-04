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
uvicorn app.main:app --host 0.0.0.0 --port 8000

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
