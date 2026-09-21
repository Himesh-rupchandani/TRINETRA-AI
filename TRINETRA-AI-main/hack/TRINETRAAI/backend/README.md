# TRINETRA AI - Enterprise Computer Vision CCTV & License Plate Intelligence Platform

[![Backend Tests](https://img.shields.io/badge/Tests-97%2F97%20Passed-brightgreen)](tests/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)]()

TRINETRA AI is an enterprise-grade video intelligence and Automated Number Plate Recognition (ANPR / ALPR) backend. It delivers real-time vehicle tracking across distributed municipal CCTV networks, automated hotlist/watchlist alerting with deduplication, GIS spatio-temporal route reconstruction, and external camera catalogue synchronization.

---

## Architecture Highlights

1. **Robust Computer Vision Ingestion**:
   - High-throughput ingestion of vehicle sightings via `POST /api/events` and `POST /api/v1/events`.
   - Dual plate field compatibility: accepts both normalized `plate` and raw `plate_raw`.
   - Microsecond video timeline synchronization with PTS (`timestamp_pts`).
   - Case-insensitive camera matching (`func.upper(Camera.camera_id) == input_cam_id.upper()`).

2. **External Sentinel Camera Catalogue Sync**:
   - Ingests and continuously updates camera registries from remote catalogues (e.g. Sentinel JSON feeds).
   - Normalizes coordinates, status, resolution, and codecs.
   - Non-blocking resilient architecture with graceful fallback to cached DB registries on upstream outages.
   - Internal administrative endpoint: `POST /api/internal/sentinel/catalogue/sync`.

3. **Multi-Camera Trace & Spatio-Temporal GIS Routing**:
   - Chronological vehicle sighting timeline across distributed camera nodes.
   - Preserves license plate detection confidence across points.
   - Ordered route point generation with latitude/longitude GIS vertices for geospatial mapping.

4. **Realtime WebSocket Broadcast & Watchlist Matching**:
   - Instant watchlist match evaluation on event ingestion.
   - Automatic 60-second alert deduplication window per camera + plate pair.
   - WebSocket streaming (`/api/ws/alerts` & `/api/v1/ws/alerts`) broadcasting frontend-compatible envelopes containing both `data` and `payload` properties.

5. **Dual Route Mounting**:
   - Universal dual route mounting under both `/api` and `/api/v1` for 100% contract compatibility.

---

## Quickstart Guide

### 1. Local Python Environment

```powershell
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
# ultralytics may install GUI OpenCV; repair cv2 for server/headless use
python ..\..\scripts\ensure_headless_opencv.py

# Run initial demo seed
python -m scripts.seed_demo

# Start the FastAPI ASGI server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Server will be running at: `http://localhost:8000`  
Swagger / OpenAPI documentation: `http://localhost:8000/docs`

---

### 2. Docker & Docker Compose

```bash
# Build and run the containerized backend
docker compose up --build -d

# Check service logs
docker compose logs -f backend

# Seed demo data inside running container
docker compose exec backend python -m scripts.seed_demo
```

---

## API Contract Reference

All endpoints are fully mounted and accessible via both `/api/...` and `/api/v1/...`.

### 1. System & Health
- - `GET /api/events/{event_id}` — Single event lookup (evidence / detection detail).
- `GET /api/stats/kpis` — Live Command Center KPIs computed from the database (no fabricated numbers).
- `GET /api/cameras/{camera_id}/stream` — Browser-safe playback ticket: same-origin WHEP path for online cameras, `playable: false` + reason otherwise. Never exposes RTSP URLs or Sentinel credentials.
- `GET /api/stream` — SSE realtime channel (same typed events as `WS /api/ws/events`).

`GET /api/health` — Full subsystem health diagnostics (Database, Watchlist, Event Ingestion, Alert Engine, Sentinel Catalogue, WebSocket Realtime Channel).
- `GET /api/` — Service root metadata.

### 2. Cameras
- `GET /api/cameras` — Normalized camera list wrapped in `{"data": [...]}` envelope:
  ```json
  {
    "data": [
      {
        "id": "cam04",
        "name": "North Gate Junction",
        "location": "Paldi Circle",
        "latitude": 23.0338,
        "longitude": 72.585,
        "status": "ONLINE",
        "codec": "H264",
        "width": 1920,
        "height": 1080,
        "stream_type": "HLS",
        "stream_url": "https://cctv.corp8.cloud/cam04/index.m3u8"
      }
    ]
  }
  ```
- `GET /api/cameras/{camera_id}` — Details for a specific camera (supports case-insensitive IDs like `cam04`, `CAM04`, or database integer IDs).

### 3. Sentinel Catalogue Sync
- `POST /api/internal/sentinel/catalogue/sync` — Synchronizes camera catalogue from remote Sentinel endpoint or direct payload.

### 4. Computer Vision Event Ingestion
- `POST /api/events` — Ingest AI detector/ANPR sighting:
  ```json
  {
    "camera_id": "cam04",
    "vehicle_id": 17,
    "plate_raw": "GJ 01 AB-1234",
    "plate": "GJ01AB1234",
    "plate_confidence": 0.94,
    "timestamp_pts": 123456.78,
    "event_time": "2026-09-02T14:32:18Z",
    "latitude": 23.0338,
    "longitude": 72.585,
    "vehicle_class": "car",
    "evidence_ref": "https://s3.example.com/snapshots/cam04_event_17.jpg"
  }
  ```

### 5. Vehicle Trace & GIS Routes
- `GET /api/vehicles/{plate_number}` — Investigation profile: sighting stats + active watchlist record (or `null`).
- `GET /api/vehicles/{plate_number}/events` — Chronological timeline of sightings for a given plate.
- `GET /api/vehicles/{plate_number}/route` — Ordered GIS route points with confidence:
  ```json
  {
    "plate_number": "GJ01AB1234",
    "total_points": 4,
    "start_time": "2026-09-02T10:00:00Z",
    "end_time": "2026-09-02T10:30:00Z",
    "points": [
      {
        "camera_id": "CAM04",
        "latitude": 23.0338,
        "longitude": 72.585,
        "timestamp": "2026-09-02T10:00:00Z",
        "confidence": 0.95
      }
    ]
  }
  ```

### 6. Watchlist Management
- `GET /api/watchlist` — List all registered hotlist vehicles.
- `POST /api/watchlist` — Add target vehicle to watchlist.
- `DELETE /api/watchlist/{id}` — Deactivate or remove watchlist entry.

### 7. Alerts Management
- `GET /api/alerts` — Paginated list of security alerts with event, camera, and plate details.
- `PATCH /api/alerts/{alert_id}/acknowledge` — Acknowledge active alert.
- `PATCH /api/alerts/{alert_id}/resolve` — Resolve active alert.

### 8. Realtime WebSockets
- `WS /api/ws/alerts` & `WS /api/v1/ws/alerts` — Real-time push notifications for watchlist alerts and system events.

---

## Running the Automated Test Suite

The test suite contains 197 automated tests covering unit logic, hardware pacing, state machines, end-to-end integration workflows and the bug-fix regression suites (`tests/test_bugfix_regressions.py`, `tests/test_speed_and_insights_regressions.py`, `tests/test_frontend_js_suite.py`).

```powershell
# Run the entire test suite
pytest -v

# Run only system integration tests
pytest tests/test_system_integration.py -v

# Run with test coverage
pytest --cov=app --cov-report=term-missing
```

Test Results Summary:
- **Total Tests**: 197
- **Passed**: 197 (100%)
- **Failed**: 0

> The frontend contract suite (48 tests, `cd trinetra-ai && npm test`) runs from pytest as well
> and is skipped automatically when `node` or the frontend `node_modules` are unavailable.
- **Errors**: 0
