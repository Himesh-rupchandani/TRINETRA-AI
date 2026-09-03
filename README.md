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

## Tests

```bash
cd TRINETRAAI/backend && pytest          # 91 tests
cd cv-engine && pytest                   # 79 offline tests (live-feed tests opt-in)
cd cv-engine && TRINETRA_LIVE=1 pytest -m live tests/test_live_sentinel.py -v
```
