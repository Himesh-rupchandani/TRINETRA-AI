"""
Stats API — live Command Center KPIs.

GET /api/stats/kpis  — dashboard counters computed from the real database.
No fabricated values: every number is derived from cameras/alerts/events rows.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta

from ..database.database import get_db
from ..database.models import Camera, Alert, VehicleEvent
from ..camera.manager import camera_manager

router = APIRouter(prefix="/stats", tags=["Stats"])


class DashboardKpis(BaseModel):
    total_cameras: int
    cameras_online: int
    cameras_degraded: int
    cameras_offline: int
    active_alerts: int
    vehicle_detections_24h: int
    anpr_reads_24h: int
    watchlist_matches_24h: int
    generated_at: datetime


@router.get("/kpis", response_model=DashboardKpis, summary="Command Center KPIs")
def get_kpis(db: Session = Depends(get_db)):
    """Aggregate KPI counters for the Command Center dashboard.

    Camera status follows the same precedence as GET /cameras: live stream
    status when the manager knows the camera, otherwise the registry value.
    """
    cameras = db.query(Camera).all()

    online = degraded = offline = 0
    for cam in cameras:
        stream_status = camera_manager.get_camera_status(cam.camera_id)
        status = (stream_status["status"] if stream_status else (cam.status or "OFFLINE")).upper()
        if status == "ONLINE":
            online += 1
        elif status in ("DEGRADED", "CONNECTING", "ERROR"):
            degraded += 1
        else:
            offline += 1

    active_alerts = (
        db.query(Alert)
        .filter(Alert.status.notin_(["RESOLVED", "DISMISSED"]))
        .count()
    )

    day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    base_24h = db.query(VehicleEvent).filter(VehicleEvent.event_time >= day_ago)
    detections_24h = base_24h.count()
    anpr_24h = base_24h.filter(VehicleEvent.plate_number.isnot(None)).count()
    matches_24h = base_24h.filter(VehicleEvent.watchlist_match.is_(True)).count()

    return DashboardKpis(
        total_cameras=len(cameras),
        cameras_online=online,
        cameras_degraded=degraded,
        cameras_offline=offline,
        active_alerts=active_alerts,
        vehicle_detections_24h=detections_24h,
        anpr_reads_24h=anpr_24h,
        watchlist_matches_24h=matches_24h,
        generated_at=datetime.now(timezone.utc),
    )
