# TRINETRA reference backend

A small FastAPI app that makes the control-room UI show **real CV events** instead
of mocks. It runs the real CV engine (YOLO11 + ByteTrack + PP-OCR) on the
controlled fixture in a background thread, POSTs its events to `POST /api/events`
through the same client a field deployment uses, then stores and serves them in
the exact contract the frontend expects.

Run (from repo root):

```bash
.venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
VITE_BACKEND_ORIGIN=http://localhost:8000 npm --prefix trinetra-ai run dev
```

and set `VITE_USE_MOCKS=false` in `trinetra-ai/.env`.

Endpoints: `POST /api/events`, `GET /api/events`, `/api/cameras`, `/api/alerts`
(+ack/resolve), `/api/watchlist`, `/api/vehicles/<plate>/{events,route,}`,
`/api/health`, `/api/stats/kpis`, `GET /api/evidence/<ref>`, and SSE `GET /api/stream`.

This is a reference/demo backend (in-memory). The production backend is a separate
deliverable; the CV -> `/api/events` wire contract is identical. Because the
government gateway is egress-blocked in this sandbox, the CV feeder runs on the
controlled fixture (real AI, labelled honestly in `/api/health`). Point
`scripts/run_pipeline.py` at a reachable Sentinel feed for the live variant.
