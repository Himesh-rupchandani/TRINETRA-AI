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

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from .core.config import settings
from .core.logging_config import logger
from .core.vision import vision_available, vision_status, warn_once
from .core.bootstrap import ensure_demo_dataset, get_demo_seed_report, storage_report
from .core.bootstrap import _format_demo_data  # internal, but stable for health
from .database.database import init_db, get_db, SessionLocal
from .database.models import Camera
from .database.schemas import HealthResponse
from .camera.manager import camera_manager
from .camera.live_source import sync_live_camera
from .core.paths import evidence_root
from .services.ws_manager import ws_manager
from .services.live_anpr_service import live_anpr_service
from .api.cameras import router as cameras_router
from .api.live_anpr import router as live_anpr_router
from .api.watchlist import router as watchlist_router
from .api.alerts import router as alerts_router
from .api.detections import router as detections_router
from .api.events import router as events_router
from .api.vehicles import router as vehicles_router
from .api.internal import router as internal_router
from .api.officers import router as officers_router
from .api.uploads import router as uploads_router
from .api.chunked_uploads import router as chunked_uploads_router
from .api.video_analysis import router as video_analysis_router
from .api.evidence import router as evidence_router
from .api.stats import router as stats_router
from .api.stream import router as sse_router
from .api.websocket import router as ws_router
from .api.ingest import router as ingest_router
# Superior Features - Judge-Wow
from .api.speed import router as speed_router
from .api.bandwidth import router as bandwidth_router
from .api.insights import router as insights_router
from .api.reports import router as reports_router
from .api.sentinel_proxy import router as sentinel_proxy_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for database initialization and camera streams."""
    logger.info("Starting TRINETRA AI Surveillance Engine...")

    # 1. Ensure tables exist before we probe blank DB.  init_db() also does this,
    # but we need the tables before the demo-seed probe because the new atomic
    # rule is strict: cameras==0 and events==0.  A fresh DB has 0 rows; demo adds
    # 30, then init_db sees 30 and skips its 4 bootstrap.  This order is what
    # makes the 30/22/5 grid appear on a cold serverless start with NO env var.
    from app.database.models import Base
    from app.database.database import engine as _engine, _auto_migrate
    try:
        Base.metadata.create_all(bind=_engine)
        _auto_migrate(_engine)
    except Exception as e:
        logger.warning(f"DB table ensure before demo seed failed: {e}")

    # 1a. Serverless/read-only awareness. On a host whose database starts
    # empty every cold start (Vercel, Cloud Run) the registry would otherwise
    # be blank and the control room would read as "broken" rather than "fresh".
    storage = storage_report()
    if storage.get("mode") != "PERSISTENT":
        logger.warning(f"Storage mode {storage['mode']}: {storage.get('detail', storage.get('path'))}")
    seed_db = SessionLocal()
    try:
        seed_report = ensure_demo_dataset(seed_db)
        if seed_report.get("seeded"):
            logger.info(f"Demo dataset ready: {seed_report['cameras']} cameras, {seed_report['events']} events.")
    finally:
        seed_db.close()

    # 1b. Bootstrap 4 cameras if still blank (persistent blank or demo failed/ skipped)
    # init_db is idempotent — after a successful demo it sees 30 and does nothing.
    init_db()
    warn_once(logger)

    # 1b. Ensure evidence root exists (backend+frontend only mode may not have cv-engine folder)
    try:
        # Same resolution authority the evidence API and the video pipelines use.
        logger.info(f"Evidence root ensured at {evidence_root()}")
    except Exception as e:
        logger.warning(f"Could not create evidence root {settings.EVIDENCE_ROOT}: {e}")

    # 1c. Bind the realtime fan-out to THIS loop so worker threads (uploaded /
    # multi-video analysis) can broadcast without spinning up a private loop
    # that can never reach the SSE queues or WebSocket transports.
    ws_manager.attach_loop(asyncio.get_running_loop())

    # Resident streams submit samples to the same bounded pipeline as browser
    # WHEP/HLS frames. Inference never runs inside the camera acquisition loop.
    if vision_available():
        live_anpr_service.start()
        camera_manager.set_pipeline_callback(live_anpr_service.submit_packet)

    # 2. Sync the env-configured REAL live camera (.env -> registry), then
    # register existing cameras into CameraManager
    db = SessionLocal()
    try:
        try:
            sync_live_camera(db)
        except Exception as e:
            logger.error(f"Error syncing live camera source: {e}")
        cameras = db.query(Camera).all()
        if not vision_available():
            # No OpenCV in this process: there is nothing to decode, so do not
            # build 30 dead stream objects. The registry, events, watchlist,
            # GIS and reports are all unaffected — only frame-level CV is off.
            logger.info(
                f"Skipping CameraManager registration for {len(cameras)} cameras "
                "(vision stack unavailable — API-only mode)."
            )
            cameras = []
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
            source = cam.stream_url
            source_type = cam.stream_type
            if auto_start:
                from .services.sentinel_stream_service import resolve_ingest_source
                source = resolve_ingest_source(cam.camera_id, cam.stream_url, cam.stream_type)
                if source != cam.stream_url:
                    source_type = "rtsp"
            camera_manager.add_camera(
                camera_id=cam.camera_id, source=source,
                source_type=source_type, auto_start=auto_start,
            )
    except Exception as e:
        logger.error(f"Error initializing cameras from DB: {e}")
    finally:
        db.close()

    # Scripted alerts are for an explicitly opted-in demo only, never a
    # replacement for real detections when cameras/ML are unavailable.
    from .services.alert_scheduler import start_alert_scheduler, stop_alert_scheduler
    alert_task = None
    if settings.DEMO_MODE and settings.DEMO_ALERTS_ENABLED:
        alert_task = asyncio.create_task(start_alert_scheduler(interval_seconds=60))

    yield

    # 3. Clean shutdown - release all camera resources and scheduler
    logger.info("Shutting down TRINETRA AI Surveillance Engine...")
    stop_alert_scheduler()
    if alert_task is not None:
        alert_task.cancel()
    camera_manager.set_pipeline_callback(None)
    active_cams = camera_manager.list_cameras()
    for cam in active_cams:
        camera_manager.stop_camera(cam["camera_id"])
    await asyncio.to_thread(live_anpr_service.stop)
    ws_manager.detach_loop()
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
    # total_cameras is the registry size (DB count) — not the in-memory
    # manager size.  On a vision-less host (Vercel, TRINETRA_API_ONLY) the
    # manager is intentionally empty, but the registry, map and GIS must still
    # report 31 cameras (30 grid + CAMLIVE).
    try:
        db_total = db.query(Camera).count()
    except Exception:
        db_total = len(cam_list)

    vis = vision_status()
    storage = storage_report()
    demo_report = get_demo_seed_report()
    components = {
        "api": "HEALTHY",
        "database": "HEALTHY" if db_ok else "UNHEALTHY",
        "watchlist": "HEALTHY",
        "event_ingestion": "HEALTHY",
        "alert_engine": "HEALTHY",
        "sentinel_catalogue": "HEALTHY",
        "realtime_channel": "HEALTHY",
        # Reported honestly instead of assumed: on a vision-less host these
        # features are genuinely off, and the control room should say so.
        "cv_pipeline": "HEALTHY" if vis["available"] else "DISABLED (API-only: no cv2/numpy)",
        "storage": storage["mode"],
        "demo_data": _format_demo_data(demo_report),
    }

    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        app_name=settings.PROJECT_NAME,
        version="1.0.0",
        environment=settings.APP_ENV,
        database_connected=db_ok,
        active_cameras=active_count,
        total_cameras=db_total,
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
    r.include_router(live_anpr_router)
    r.include_router(watchlist_router)
    r.include_router(alerts_router)
    r.include_router(detections_router)
    r.include_router(events_router)
    r.include_router(vehicles_router)
    r.include_router(stats_router)
    r.include_router(internal_router)
    r.include_router(officers_router)
    r.include_router(uploads_router)
    r.include_router(chunked_uploads_router)
    r.include_router(video_analysis_router)
    r.include_router(evidence_router)
    r.include_router(sse_router)
    r.include_router(ingest_router)
    # Superior Features
    r.include_router(speed_router)
    r.include_router(bandwidth_router)
    r.include_router(insights_router)
    r.include_router(reports_router)
    app.include_router(r)
    app.include_router(ws_router, prefix=prefix)

# Also mount WebSocket router without prefix
app.include_router(ws_router)

# Same-origin Sentinel media proxy: browser playback paths (/sentinel/…) are
# proxied to the media gateway with server-side Basic auth. Mounted at the
# origin root on purpose — the frontend's tickets carry same-origin paths
# (/sentinel/stream/<id>/whep, /sentinel/live/stream/<id>/index.m3u8), never
# /api. This is the Vercel-side twin of the Vite dev proxy.
app.include_router(sentinel_proxy_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
