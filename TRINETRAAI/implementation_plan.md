# Implementation Plan: TRINETRA AI Backend

Build a complete, operational, production-ready backend for **TRINETRA AI ("Intelligent Vision. Faster Response.")** — a CCTV Intelligence & Investigation Platform.

---

## User Review Required

> [!IMPORTANT]
> **Database Flexibility**: The backend is configured to seamlessly support both **PostgreSQL (with PostGIS)** in production/Docker and **SQLite** locally for frictionless developer onboarding.
>
> **Core Demo Flow Guaranteed**:
> `POST /api/events` with plate `GJ 01 AB-1234` $\rightarrow$ Normalized to `GJ01AB1234` $\rightarrow$ Watchlist match (`STOLEN`) $\rightarrow$ Real-time alert generated with deduplication $\rightarrow$ `GET /api/vehicles/GJ01AB1234/events` (4 sightings: `CAM04`, `CAM08`, `CAM12`, `CAM17`) $\rightarrow$ `GET /api/vehicles/GJ01AB1234/route` (GIS coordinates for map display).

---

## Architecture Overview

```
Sentinel / CCTV Sources ──► Camera Registry (30+ Cameras)
                                  │
AI/CV Ingestion Engine ───────────┴──► POST /api/events
                                              │
                                              ▼
                                     Plate Normalizer ("GJ 01 AB-1234" -> "GJ01AB1234")
                                              │
                                              ▼
                                     Store Vehicle Event
                                              │
                                     Watchlist Matching Service
                                     ┌────────┴────────┐
                                    MATCH            NO MATCH
                                     │                 │
                           Alert Deduplication    Normal Event
                           (Cooldown window)           │
                                     │                 │
                               Create Alert            │
                                     │                 │
                         WebSocket /api/ws/events ◄────┘
                                     │
               Frontend Dashboard / Vehicle Investigation + GIS Route
```

---

## Proposed Changes

### 1. Core Configuration, Logging & Security (`backend/app/core/`)

#### [NEW] [config.py](file:///c:/Users/subha/AppData/Roaming/Microsoft/Windows/Network%20Shortcuts/SUBH%20%21/TRINETRAAI/backend/app/core/config.py)
- Centralized `BaseSettings` with environment variable loading.
- Database URL (Postgres / SQLite fallback), Alert deduplication cooldown (`ALERT_DEDUP_COOLDOWN_SECONDS = 180`), Sentinel catalogue URL (`https://cctv.corp8.cloud/cameras.json`), CORS origins, JWT secret key, Redis URL.

#### [NEW] [logging.py](file:///c:/Users/subha/AppData/Roaming/Microsoft/Windows/Network%20Shortcuts/SUBH%20%21/TRINETRAAI/backend/app/core/logging.py)
- Structured logging format capturing event intake, validation errors, watchlist matches, alert creation, alert acknowledgement, camera status transitions, and Sentinel sync.

#### [NEW] [security.py](file:///c:/Users/subha/AppData/Roaming/Microsoft/Windows/Network%20Shortcuts/SUBH%20%21/TRINETRAAI/backend/app/core/security.py)
- Auth & RBAC primitives (`ADMIN`, `SUPERVISOR`, `INVESTIGATOR`, `OPERATOR`), token validation dependencies, and secure audit helpers.

---

### 2. Database Models & Alembic Migrations (`backend/app/db/` & `backend/alembic/`)

#### [NEW] [database.py](file:///c:/Users/subha/AppData/Roaming/Microsoft/Windows/Network%20Shortcuts/SUBH%20%21/TRINETRAAI/backend/app/db/database.py)
- SQLAlchemy 2.0 engine, `SessionLocal`, base declarative class, session dependency.

#### [NEW] Models in `backend/app/db/models/`
- **`camera.py`**: `Camera` table (`id`, `name`, `department`, `location_name`, `latitude`, `longitude`, `status`, `codec`, `width`, `height`, `stream_type`, `stream_url`, `last_seen`, `created_at`, `updated_at`).
- **`event.py`**: `VehicleEvent` table (`id`, `camera_id` FK, `vehicle_track_id`, `plate_raw`, `plate_number`, `plate_confidence`, `vehicle_class`, `event_time`, `event_time_pts`, `latitude`, `longitude`, `evidence_ref`, `watchlist_match`, `created_at`) with indexes on `(plate_number, camera_id, event_time)`.
- **`watchlist.py`**: `Watchlist` table (`id`, `plate_number` indexed, `category`, `priority`, `reason`, `status`, `created_at`, `updated_at`).
- **`alert.py`**: `Alert` table (`id`, `event_id` FK, `watchlist_id` FK, `plate_number`, `camera_id`, `severity`, `status` indexed, `message`, `created_at` indexed, `acknowledged_at`, `acknowledged_by`, `resolved_at`, `resolved_by`).
- **`user.py`**: `User` table (`id`, `name`, `email`, `role`, `status`, `created_at`).
- **`audit.py`**: `AuditLog` table (`id`, `user_id`, `action`, `resource_type`, `resource_id`, `timestamp`, `metadata`).

#### [NEW] Alembic configuration & initial migration
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, initial migration script creating all tables and performance indexes.

---

### 3. Pydantic Schemas (`backend/app/schemas/`)

#### [NEW] `camera.py`, `event.py`, `vehicle.py`, `watchlist.py`, `alert.py`, `system.py`
- Standardized request/response models with consistent metadata pagination wrapper (`data`, `meta: { page, limit, total }`) and structured error responses.

---

### 4. Utilities (`backend/app/utils/`)

#### [NEW] [plate_normalizer.py](file:///c:/Users/subha/AppData/Roaming/Microsoft/Windows/Network%20Shortcuts/SUBH%20%21/TRINETRAAI/backend/app/utils/plate_normalizer.py)
- Reusable plate normalization function:
  - Input: `"GJ 01 AB-1234"` $\rightarrow$ Output: `"GJ01AB1234"`
  - Uppercase, removes spaces, hyphens, punctuation.
  - Retains raw OCR string and confidence separately.

---

### 5. Domain Services (`backend/app/services/`)

#### [NEW] Domain Service Layer
- **`event_service.py`**: Handles event ingestion pipeline (validate camera, validate coordinates, validate confidence $0 \le c \le 1$, normalize plate, persist event, invoke watchlist matcher, invoke alert generator with deduplication, push event to WebSocket).
- **`watchlist_service.py`**: Normalized plate lookup, CRUD operations, watchlist category & priority management.
- **`alert_service.py`**: Alert generation with deduplication cooldown window (checks if identical plate + camera + watchlist item alerted within last $N$ seconds), alert acknowledge (`NEW` $\rightarrow$ `ACKNOWLEDGED`), alert resolve.
- **`vehicle_service.py`**: Chronological cross-camera vehicle history search (`/api/vehicles/{plate}/events`).
- **`route_service.py`**: GIS detection route extraction (`/api/vehicles/{plate}/route`) returning ordered geographic coordinates.
- **`camera_service.py`**: Camera registry queries, filtering, search, status synchronization.
- **`sentinel_service.py`**: Sentinel catalogue fetch & upsert synchronization (`https://cctv.corp8.cloud/cameras.json`).

---

### 6. API Routes & WebSockets (`backend/app/api/`)

#### [NEW] REST & Real-time Endpoints
- **`POST /api/events`**: AI Event ingestion endpoint.
- **`GET /api/events`**: Paginated event query with filters.
- **`GET /api/vehicles/{plate}/events`**: Vehicle cross-camera history.
- **`GET /api/vehicles/{plate}/route`**: GIS route points.
- **`GET /api/cameras`**, **`GET /api/cameras/{id}`**: Camera registry.
- **`GET /api/watchlist`**, **`POST /api/watchlist`**, **`GET /api/watchlist/{id}`**, **`PUT /api/watchlist/{id}`**, **`DELETE /api/watchlist/{id}`**: Watchlist management.
- **`GET /api/alerts`**, **`POST /api/alerts/{id}/ack`**, **`POST /api/alerts/{id}/resolve`**: Alert management.
- **`GET /api/health`**: Subsystem diagnostic health checks.
- **`GET /api/internal/sentinel/catalogue/sync`**: Sentinel catalogue sync.
- **`WebSocket /api/ws/events`**: Live event stream for `VEHICLE_DETECTED`, `WATCHLIST_MATCH`, `ALERT_CREATED`, `CAMERA_STATUS_CHANGED`.

---

### 7. Seed & Demo Data (`backend/seed/` & `backend/scripts/`)

#### [NEW] [seed_demo.py](file:///c:/Users/subha/AppData/Roaming/Microsoft/Windows/Network%20Shortcuts/SUBH%20%21/TRINETRAAI/backend/scripts/seed_demo.py)
- Seeds 30 cameras with realistic CCTV metadata & coordinates.
- Seeds 10 watchlist records (including `GJ01AB1234` as `STOLEN`, priority `CRITICAL`).
- Seeds 20+ vehicle events, including the primary demo journey for `GJ01AB1234` across `CAM04` $\rightarrow$ `CAM08` $\rightarrow$ `CAM12` $\rightarrow$ `CAM17`.
- Seeds 5 realistic alerts.

---

### 8. Docker & Documentation (`Dockerfile`, `docker-compose.yml`, `README.md`)

#### [NEW] [docker-compose.yml](file:///c:/Users/subha/AppData/Roaming/Microsoft/Windows/Network%20Shortcuts/SUBH%20%21/TRINETRAAI/backend/docker-compose.yml) & [Dockerfile](file:///c:/Users/subha/AppData/Roaming/Microsoft/Windows/Network%20Shortcuts/SUBH%20%21/TRINETRAAI/backend/Dockerfile)
- PostgreSQL + PostGIS service and FastAPI backend service.

---

## Verification Plan

### Automated Tests
Run pytest covering all core business logic and integrations:
```powershell
pytest -v
```
1. `tests/test_plate_normalizer.py`: Tests "GJ 01 AB-1234" -> "GJ01AB1234", punctuation, whitespace handling.
2. `tests/test_event_ingestion.py`: Tests ingestion validation, rejection of invalid cameras/coordinates/confidence.
3. `tests/test_watchlist_match.py`: Tests watchlist lookup on event intake.
4. `tests/test_alert_dedup.py`: Tests alert creation on match and cooldown deduplication.
5. `tests/test_vehicle_search_route.py`: Tests `/api/vehicles/{plate}/events` and `/api/vehicles/{plate}/route`.
6. `tests/test_health.py`: Tests `/api/health` subsystem reporting.
7. `tests/test_cctv_streaming.py`: Retains all 13 CCTV streaming engine tests.

### Manual Verification
1. Run `python -m scripts.seed_demo` to seed the database.
2. Start server via `python -m uvicorn app.main:app --reload`.
3. Ingest a new vehicle event:
   ```bash
   curl -X POST http://127.0.0.1:8000/api/events -H "Content-Type: application/json" -d '{"camera_id":"CAM04","vehicle_id":101,"plate_raw":"GJ 01 AB-1234","plate_confidence":0.95,"event_time":"2026-09-02T14:00:00Z","latitude":23.0338,"longitude":72.585,"vehicle_class":"car"}'
   ```
4. Query vehicle events & GIS route:
   ```bash
   curl http://127.0.0.1:8000/api/vehicles/GJ01AB1234/events
   curl http://127.0.0.1:8000/api/vehicles/GJ01AB1234/route
   ```
5. Verify `/docs` Swagger UI renders all schemas and endpoints cleanly.
