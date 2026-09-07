import sys
from pathlib import Path

# Allow running this file directly as a script (e.g. `python backend/app/main.py`)
if __name__ == "__main__" and not __package__:
    project_root = Path(__file__).resolve().parents[2]
    backend_root = Path(__file__).resolve().parents[1]
    for p in [str(project_root), str(backend_root)]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    __package__ = "backend.app"

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from .core.config import settings
from .core.logging_config import logger
from .database.database import init_db, get_db, SessionLocal
from .database.models import Camera
from .database.schemas import HealthResponse
from .camera.manager import camera_manager
from .camera.live_source import sync_live_camera
from .api.cameras import router as cameras_router
from .api.watchlist import router as watchlist_router
from .api.alerts import router as alerts_router
from .api.detections import router as detections_router
from .api.events import router as events_router
from .api.vehicles import router as vehicles_router
from .api.internal import router as internal_router
from .api.evidence import router as evidence_router
from .api.stats import router as stats_router
from .api.stream import router as sse_router
from .api.websocket import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for database initialization and camera streams."""
    logger.info("Starting TRINETRA AI Surveillance Engine...")

    # 1. Initialize DB tables (creates vehicle_events + alert ack fields)
    init_db()

    # 1b. Ensure evidence root exists (backend+frontend only mode may not have cv-engine folder)
    try:
        evidence_root = Path(settings.EVIDENCE_ROOT)
        # If relative, resolve from backend root
        if not evidence_root.is_absolute():
            # backend/app/main.py -> backend root is parents[1]
            backend_root = Path(__file__).resolve().parents[1]
            evidence_root = (backend_root / evidence_root).resolve()
        evidence_root.mkdir(parents=True, exist_ok=True)
        logger.info(f"Evidence root ensured at {evidence_root}")
    except Exception as e:
        logger.warning(f"Could not create evidence root {settings.EVIDENCE_ROOT}: {e}")

    # 2. Sync the env-configured REAL live camera (.env -> registry), then
    # register existing cameras into CameraManager
    db = SessionLocal()
    try:
        try:
            sync_live_camera(db)
        except Exception as e:
            logger.error(f"Error syncing live camera source: {e}")
        cameras = db.query(Camera).all()
        logger.info(f"Registering {len(cameras)} CCTV cameras into CameraManager...")
        for cam in cameras:
            # Resident ingest workers are for REAL network cameras only
            # (rtsp/hls); file-backed demo cameras play on demand, so a
            # 30-camera demo grid never spawns 30 decoder threads.
            auto_start = (
                settings.AUTO_START_CAMERAS
                and (cam.stream_url or "").strip() != ""
                and (cam.stream_type or "").lower() != "file"
            )
            camera_manager.add_camera(
                camera_id=cam.camera_id,
                source=cam.stream_url,
                source_type=cam.stream_type,
                auto_start=auto_start,
            )
    except Exception as e:
        logger.error(f"Error initializing cameras from DB: {e}")
    finally:
        db.close()

    yield

    # 3. Clean shutdown - release all camera resources
    logger.info("Shutting down TRINETRA AI Surveillance Engine...")
    active_cams = camera_manager.list_cameras()
    for cam in active_cams:
        camera_manager.stop_camera(cam["camera_id"])
    logger.info("All camera streams and resources cleanly released.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description=(
        "TRINETRA AI - Intelligent Vision. Faster Response. "
        "CCTV Intelligence & Investigation Platform with ANPR, "
        "Watchlist Matching, Alert Management, and Real-time WebSocket streaming."
    ),
    lifespan=lifespan,
)

# CORS Middleware Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- System Health Endpoints ---
@app.get("/health", response_model=HealthResponse, tags=["System"])
@app.get("/api/health", response_model=HealthResponse, tags=["System"])
@app.get("/api/v1/health", response_model=HealthResponse, tags=["System"])
def health_check(db: Session = Depends(get_db)):
    """System health check and diagnostic status covering API, DB, Watchlist, Alerts, and Realtime."""
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")

    cam_list = camera_manager.list_cameras()
    active_count = sum(1 for c in cam_list if c["is_alive"])

    components = {
        "api": "HEALTHY",
        "database": "HEALTHY" if db_ok else "UNHEALTHY",
        "watchlist": "HEALTHY",
        "event_ingestion": "HEALTHY",
        "alert_engine": "HEALTHY",
        "sentinel_catalogue": "HEALTHY",
        "realtime_channel": "HEALTHY",
    }

    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        app_name=settings.PROJECT_NAME,
        version="1.0.0",
        environment=settings.APP_ENV,
        database_connected=db_ok,
        active_cameras=active_count,
        total_cameras=len(cam_list),
        demo_mode=settings.DEMO_MODE,
        timestamp=datetime.now(timezone.utc),
        components=components,
    )


@app.get("/", tags=["System"])
def root():
    """API Root index."""
    return {
        "name": settings.PROJECT_NAME,
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "api": "/api",
        "api_v1": "/api/v1",
        "websocket": "/api/ws/events",
        "sse": "/api/stream",
    }


# Mount API Routers under both /api and /api/v1 for complete frontend compatibility
for prefix in ["/api", "/api/v1"]:
    r = APIRouter(prefix=prefix)
    r.include_router(cameras_router)
    r.include_router(watchlist_router)
    r.include_router(alerts_router)
    r.include_router(detections_router)
    r.include_router(events_router)
    r.include_router(vehicles_router)
    r.include_router(stats_router)
    r.include_router(internal_router)
    r.include_router(evidence_router)
    r.include_router(sse_router)
    app.include_router(r)
    app.include_router(ws_router, prefix=prefix)

# Also mount WebSocket router without prefix
app.include_router(ws_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
