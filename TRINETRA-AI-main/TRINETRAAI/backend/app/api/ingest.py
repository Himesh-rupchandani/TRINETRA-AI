"""
Unified Ingest API — exposes all 4 Sentinel stream types in one place.

User requested:
🤖 AI processing      rtsp://<host>:8554/stream/<id>
🌐 Browser preview    http://<host>:8889/stream/<id>/whep
📺 Dashboard/mobile   http://<host>/live/stream/<id>/index.m3u8  (and CDN HLS)
📋 Camera catalogue   http://<host>/api/ingest  (catalogue + sync)

All credentials are built server-side only, never returned to client
unless explicitly redacted. RTSP authenticated URL is never exposed via API
— only its existence and redacted form are returned. Browser and mobile
clients always receive same-origin proxied paths.

This router is mounted at /api/ingest and /api/v1/ingest.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..core.config import settings
from ..core.logging_config import logger
from ..database.database import get_db
from ..database.models import Camera
from ..database.camera_directory import restore_sentinel_directory
from ..core.vision import vision_available
from ..camera.manager import camera_manager
from ..services.sentinel_catalogue_service import sync_sentinel_catalogue, fetch_catalogue
from ..services.sentinel_stream_service import (
    get_whep_path,
    get_whep_gateway_url,
    get_hls_url,
    get_hls_live_gateway_url,
    get_hls_live_path,
    get_rtsp_url,
    credentials_configured,
    redact,
    is_sentinel_camera,
    resolve_ingest_source,
)

router = APIRouter(prefix="/ingest", tags=["Ingest — Unified Sentinel API"])


@router.get(
    "",
    summary="📋 Unified Ingest API overview — GET /api/ingest",
    description="Returns overview of all 4 Sentinel APIs: RTSP AI, WHEP browser, HLS mobile, catalogue",
)
def ingest_overview(db: Session = Depends(get_db)):
    cameras = db.query(Camera).count()
    return {
        "message": "TRINETRA AI — Unified Ingest API",
        "total_cameras": cameras,
        "apis": {
            "ai_processing": {
                "description": "🤖 AI processing — CV engine consumes RTSP",
                "format": "rtsp://<host>:8554/stream/<id>",
                "example": f"rtsp://{settings.SENTINEL_RTSP_HOST}:{settings.SENTINEL_RTSP_PORT}/stream/cam04",
                "endpoint": "/api/ingest/streams/{camera_id}",
                "usage": "Backend builds authenticated URL at connect time: rtsp://email:password@host:8554/stream/cam04",
            },
            "browser_preview": {
                "description": "🌐 Browser preview — WebRTC WHEP",
                "format": "http://<host>:8889/stream/<id>/whep",
                "example": f"http://{settings.SENTINEL_RTSP_HOST}:8889/stream/cam04/whep",
                "same_origin": "/sentinel/stream/cam04/whep",
                "endpoint": "/api/ingest/preview/{camera_id}",
                "frontend": "useWhepStream('/sentinel/stream/cam04/whep', active)",
            },
            "dashboard_mobile": {
                "description": "📺 Dashboard/mobile — HLS",
                "format": "http://<host>/live/stream/<id>/index.m3u8",
                "example": f"http://{settings.SENTINEL_RTSP_HOST}/live/stream/cam04/index.m3u8",
                "same_origin": "/sentinel/live/stream/cam04/index.m3u8",
                "cdn": "https://cctv.corp8.cloud/cam04/index.m3u8",
                "endpoint": "/api/ingest/hls/{camera_id}",
                "frontend": "useHlsStream('/sentinel/live/stream/cam04/index.m3u8', active)",
            },
            "camera_catalogue": {
                "description": "📋 Camera catalogue — list + sync",
                "format": "http://<host>/api/ingest",
                "endpoints": [
                    "GET /api/ingest/catalogue — list cameras",
                    "GET /api/ingest/catalogue?sync=true — sync from Sentinel",
                    "POST /api/ingest/sync — trigger sync",
                    "GET /api/ingest/health — health of all 4",
                ],
                "sentinel_source": settings.SENTINEL_CATALOGUE_URL,
            },
        },
        "auto_login": True,
        "credentials_configured": credentials_configured(),
        "note": "All 4 use same SENTINEL_EMAIL/PASSWORD from .env — auto-injected, no manual login",
    }


def _get_camera_or_404(camera_id: str, db: Session) -> Camera:
    cam = (
        db.query(Camera)
        .filter(func.upper(Camera.camera_id) == camera_id.strip().upper())
        .first()
    )
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )
    return cam


@router.get(
    "/catalogue",
    summary="📋 Camera catalogue — GET /api/ingest/catalogue",
    description="Returns full camera registry (DB) and optionally syncs from Sentinel catalogue (cameras.json). Same as GET /api/cameras but with ingest metadata.",
)
def get_catalogue(
    sync: bool = False,
    db: Session = Depends(get_db),
):
    """
    📋 Camera catalogue API
    - sync=false: returns DB registry (30 cameras)
    - sync=true: fetches https://cctv.corp8.cloud/cameras.json then upserts
    """
    if sync:
        try:
            result = sync_sentinel_catalogue(db)
            return {
                "source": "sentinel" if result["status"] == "success" else "database",
                "synced": result["status"] == "success",
                "catalogue_url": settings.SENTINEL_CATALOGUE_URL,
                **result,
            }
        except Exception as e:
            logger.warning(f"[INGEST] catalogue sync failed: {e}")
            # fall through to DB

    cameras = db.query(Camera).all()
    return {
        "source": "database",
        "synced": False,
        "catalogue_url": settings.SENTINEL_CATALOGUE_URL,
        "total_cameras": len(cameras),
        "cameras": [
            {
                "id": c.camera_id.lower(),
                "camera_id": c.camera_id,
                "name": c.name,
                "location": c.location,
                "latitude": c.latitude,
                "longitude": c.longitude,
                "status": c.status,
                "stream_type": c.stream_type,
                "stream_url": c.stream_url,
                "department": c.department,
                "zone": c.zone,
            }
            for c in cameras
        ],
    }


@router.post(
    "/sync",
    summary="📋 Sync camera catalogue — POST /api/ingest/sync",
    description="Triggers Sentinel catalogue sync (https://cctv.corp8.cloud/cameras.json). Same as POST /api/internal/sentinel/catalogue/sync.",
)
def sync_catalogue_endpoint(db: Session = Depends(get_db)):
    result = sync_sentinel_catalogue(db)
    return result


@router.post("/restore-camera-list", summary="Restore missing entries from the bundled 30-camera directory")
def restore_camera_list(db: Session = Depends(get_db)):
    """Metadata only. Never overwrites an existing camera or inserts demo events."""
    result = restore_sentinel_directory(db)
    db.commit()
    runtime_warnings = []
    if vision_available():
        for camera_id in result.get("added_ids", []):
            try:
                camera = db.query(Camera).filter(Camera.camera_id == camera_id).first()
                if camera:
                    camera_manager.add_camera(camera_id=camera.camera_id, source=camera.stream_url,
                                              source_type=camera.stream_type, auto_start=False)
            except Exception:
                runtime_warnings.append(camera_id)
    if runtime_warnings:
        result["runtime_registration_warnings"] = runtime_warnings
        result["message"] += " Some runtime handles need a backend restart; camera entries are saved."
    return result


@router.get(
    "/streams/{camera_id}",
    summary="Unified stream URLs for a camera — all 4 types",
    description=(
        "Returns all stream URL formats for one camera:\n"
        "- 🤖 AI: rtsp://<host>:8554/stream/<id> (backend only, redacted in response)\n"
        "- 🌐 Browser: http://<host>:8889/stream/<id>/whep + same-origin /sentinel/stream/<id>/whep\n"
        "- 📺 HLS: http://<host>/live/stream/<id>/index.m3u8 + CDN https://cctv.corp8.cloud/<id>/index.m3u8 + same-origin /sentinel/live/...\n"
    ),
)
def get_all_streams(camera_id: str, db: Session = Depends(get_db)):
    cam = _get_camera_or_404(camera_id, db)
    cid = cam.camera_id.lower()
    cid_upper = cam.camera_id.upper()

    # Sentinel host info
    rtsp_host = settings.SENTINEL_RTSP_HOST.strip()
    rtsp_port = int(settings.SENTINEL_RTSP_PORT)

    # --- 🤖 AI processing: RTSP ---
    # User requested: rtsp://<host>:8554/stream/<id>
    rtsp_redacted = None
    rtsp_public = f"rtsp://{rtsp_host}:{rtsp_port}/stream/{cid}"
    if credentials_configured() and is_sentinel_camera(cam.stream_url):
        try:
            full = get_rtsp_url(cid)
            # Only the redacted form is ever returned — never expose real creds.
            rtsp_redacted = redact(full)
            logger.info(f"[{cid_upper}] RTSP ingest resolved {rtsp_redacted}")
        except Exception as e:
            logger.warning(f"[{cid_upper}] RTSP build failed: {e}")

    # --- 🌐 Browser preview: WHEP ---
    # User requested: http://<host>:8889/stream/<id>/whep
    whep_gateway = get_whep_gateway_url(cid)
    whep_same_origin = get_whep_path(cid)  # /sentinel/stream/<id>/whep

    # --- 📺 Dashboard/mobile: HLS ---
    # User requested: http://<host>/live/stream/<id>/index.m3u8
    hls_live_gateway = get_hls_live_gateway_url(cid)
    hls_live_same_origin = get_hls_live_path(cid)
    # CDN HLS (existing)
    hls_cdn = get_hls_url(cid)  # https://cctv.corp8.cloud/<id>/index.m3u8
    hls_cdn_same_origin = f"/sentinel/live/{cid}/index.m3u8"

    # Resolve ingest source (what backend actually uses)
    ingest_source = resolve_ingest_source(cam.camera_id, cam.stream_url, cam.stream_type)
    ingest_redacted = redact(ingest_source) if ingest_source else ""

    return {
        "camera_id": cid,
        "camera_name": cam.name,
        "location": cam.location,
        "status": cam.status,
        "credentials_configured": credentials_configured(),
        "streams": {
            "ai_processing": {
                "description": "🤖 AI processing — backend CV engine consumes this RTSP",
                "rtsp_public": rtsp_public,
                "rtsp_authenticated_redacted": rtsp_redacted or rtsp_public,
                "rtsp_authenticated_exists": bool(rtsp_redacted),
                "note": "Authenticated URL built at connect time from SENTINEL_EMAIL/PASSWORD, never stored in DB or returned",
                "example": f"rtsp://<email>:<password>@{rtsp_host}:{rtsp_port}/stream/{cid}",
                "backend_ingest_source_redacted": ingest_redacted,
            },
            "browser_preview": {
                "description": "🌐 Browser preview — WebRTC WHEP, same-origin proxied, no credentials in bundle",
                "whep_gateway": whep_gateway,
                "whep_same_origin": whep_same_origin,
                "example": f"http://{rtsp_host}:8889/stream/{cid}/whep",
                "proxy": "/sentinel/stream/<id>/whep -> http://103.250.160.189:8889/stream/<id>/whep (Basic Auth injected server-side)",
            },
            "dashboard_mobile": {
                "description": "📺 Dashboard/mobile — HLS compatibility stream",
                "hls_live_gateway": hls_live_gateway,
                "hls_live_same_origin": hls_live_same_origin,
                "hls_cdn": hls_cdn,
                "hls_cdn_same_origin": hls_cdn_same_origin,
                "example": f"http://{rtsp_host}/live/stream/{cid}/index.m3u8",
                "proxy": "/sentinel/live/... -> http://<host>/live/... (Basic Auth injected)",
            },
        },
        "usage": {
            "ai": f"cv-engine: python scripts/run_pipeline.py --mode live --camera {cid}",
            "browser": f"Frontend: useWhepStream('{whep_same_origin}', active)",
            "hls": f"Frontend HLS fallback: useHlsStream('{hls_live_same_origin}', active)",
            "catalogue": "GET /api/ingest/catalogue?sync=true",
        },
    }


@router.get(
    "/preview/{camera_id}",
    summary="🌐 Browser preview ticket — GET /api/ingest/preview/{id}",
    description="Same as GET /api/cameras/{id}/stream but under /ingest namespace. Returns WHEP same-origin path.",
)
def get_preview_ticket(camera_id: str, db: Session = Depends(get_db)):
    cam = _get_camera_or_404(camera_id, db)
    cid = cam.camera_id.lower()
    whep_path = get_whep_path(cid)
    whep_gateway = f"http://{settings.SENTINEL_RTSP_HOST}:8889/stream/{cid}/whep"
    return {
        "camera_id": cid,
        "name": cam.name,
        "location": cam.location,
        "status": cam.status,
        "browser_preview": {
            "whep_same_origin": whep_path,
            "whep_gateway": whep_gateway,
            "type": "WEBRTC",
            "playable": (cam.status or "").upper() == "ONLINE",
        },
    }


@router.get(
    "/hls/{camera_id}",
    summary="📺 HLS stream URLs — GET /api/ingest/hls/{id}",
    description="Returns HLS URLs for dashboard/mobile: http://<host>/live/stream/<id>/index.m3u8 and CDN variant.",
)
def get_hls_streams(camera_id: str, db: Session = Depends(get_db)):
    cam = _get_camera_or_404(camera_id, db)
    cid = cam.camera_id.lower()
    host = settings.SENTINEL_RTSP_HOST.strip()
    return {
        "camera_id": cid,
        "name": cam.name,
        "hls": {
            "live_gateway": f"http://{host}/live/stream/{cid}/index.m3u8",
            "live_same_origin": f"/sentinel/live/stream/{cid}/index.m3u8",
            "cdn": get_hls_url(cid),
            "cdn_same_origin": f"/sentinel/live/{cid}/index.m3u8",
            "note": "Both are proxied via vite dev server / reverse proxy with Basic Auth, so browser stays same-origin, no mixed content",
        },
    }


@router.get(
    "/health",
    summary="Ingest health — all 4 APIs",
    description="Checks if Sentinel credentials are configured and if catalogue is reachable.",
)
def ingest_health(db: Session = Depends(get_db)):
    catalogue_ok = False
    catalogue_error = None
    cameras_count = db.query(Camera).count()
    try:
        fetch_catalogue(settings.SENTINEL_CATALOGUE_URL)
        catalogue_ok = True
    except ValueError as exc:
        catalogue_error = str(exc)
    except Exception as exc:
        catalogue_error = f"Catalogue request failed ({type(exc).__name__})."

    return {
        "credentials_configured": credentials_configured(),
        "sentinel_host": settings.SENTINEL_RTSP_HOST,
        "rtsp_port": settings.SENTINEL_RTSP_PORT,
        "whep_origin": f"http://{settings.SENTINEL_RTSP_HOST}:8889",
        "hls_base": settings.SENTINEL_HLS_BASE_URL,
        "catalogue_url": settings.SENTINEL_CATALOGUE_URL,
        "catalogue_reachable": catalogue_ok,
        "catalogue_error": catalogue_error,
        "total_cameras": cameras_count,
        "apis": {
            "ai_processing": f"rtsp://{settings.SENTINEL_RTSP_HOST}:{settings.SENTINEL_RTSP_PORT}/stream/<id>",
            "browser_preview": f"http://{settings.SENTINEL_RTSP_HOST}:8889/stream/<id>/whep",
            "dashboard_mobile": f"http://{settings.SENTINEL_RTSP_HOST}/live/stream/<id>/index.m3u8",
            "camera_catalogue": "/api/ingest/catalogue?sync=true",
        },
        "auto_login": True,
        "note": "All 4 APIs use same SENTINEL_EMAIL/PASSWORD from .env — auto-injected, no manual login",
    }
